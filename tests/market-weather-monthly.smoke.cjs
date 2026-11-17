// Uses a local verified private bundle. Never writes data or approved/public flags.
const {chromium}=require('playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const base=process.env.MONTHLY_PREVIEW_URL||'http://127.0.0.1:8044';
const out=path.resolve(process.env.MONTHLY_PREVIEW_SCREENSHOTS||'/tmp/currentourism-monthly-private');
assert.ok(!out.startsWith(path.resolve(__dirname,'..')+path.sep),'Screenshots must stay outside repository');
fs.mkdirSync(out,{recursive:true,mode:0o700});
(async()=>{
  const browser=await chromium.launch({headless:true}),summary={widths:[],a11y:[],states:[]};
  try{
    for(const width of [320,390,768,1440]){
      const context=await browser.newContext({viewport:{width,height:1100},reducedMotion:'reduce'}),page=await context.newPage(),errors=[],requests=[];
      page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>requests.push(r.url()));
      await page.goto(base);await page.locator('.axis').first().waitFor();
      const payload=await page.evaluate(async()=>await(await fetch('/api/preview')).json());
      assert.equal(payload.state,'private_review','For empty-preview tests run without this actual-data smoke');
      assert.equal(payload.diagnostic.supporting,undefined,'Do not send unneeded supporting series to the UI');
      assert.equal(await page.locator('.axis').count(),2);
      for(const key of ['kto_inbound','kto_tourism_receipts']){
        const axis=page.locator(`[data-axis="${key}"]`),row=payload.diagnostic.axes[key];
        assert.equal(await axis.locator('.value').textContent(),new Intl.NumberFormat('ko-KR').format(row.value));
        const expectedRate=raw=>raw===null?'비교 불가':(Number(raw)>0?'+':'')+Number(raw).toFixed(2)+'%';
        assert.deepEqual(await axis.locator('.rates dd').allTextContents(),[expectedRate(row.comparisons.yoy_pct),expectedRate(row.comparisons.mom_pct)]);
        assert.equal(await axis.locator('svg circle').count(),payload.history[key].filter(r=>Number.isSafeInteger(r.value)).length);
        assert.equal(await axis.locator('.source a').getAttribute('href'),new URL(row.provenance.source_url).href);
      }
      assert.match(await page.locator('#overall-heading').textContent(),/종합 판정 보류/);
      assert.equal(await page.locator('.evidence-list li').count(),2);
      assert.match(await page.locator('.metadata').textContent(),/미발행/);
      assert.deepEqual(await page.evaluate(async()=>{const {formatRate}=await import('/monthly.js');return ['1.005000','-1.005000','-0.000001',null].map(formatRate);}),['+1.01%','-1.01%','0.00%','비교 불가']);
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
      assert.ok(requests.every(url=>url.startsWith(base+'/')),'No external requests');
      for(const a of await page.locator('a[target="_blank"]').all())assert.match(await a.getAttribute('rel'),/noopener/);
      // First keyboard target is the skip link. Disclosure tables work without a mouse.
      await page.keyboard.press('Tab');assert.equal(await page.evaluate(()=>document.activeElement.className),'skip');
      await page.keyboard.press('Enter');assert.equal(await page.evaluate(()=>document.activeElement.id),'report');
      const disclosure=page.locator('.plot details').first();await disclosure.locator('summary').focus();await page.keyboard.press('Enter');
      assert.equal(await disclosure.evaluate(e=>e.open),true);await page.keyboard.press('Enter');
      if(process.env.MONTHLY_AXE_SOURCE){
        await page.route('**/axe-test-only.js',r=>r.fulfill({contentType:'text/javascript',body:fs.readFileSync(process.env.MONTHLY_AXE_SOURCE,'utf8')}));
        await page.addScriptTag({url:base+'/axe-test-only.js'});
        const result=await page.evaluate(async()=>{const r=await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}});return r.violations.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.map(n=>n.target)}));});
        assert.deepEqual(result,[],'axe violations: '+JSON.stringify(result));summary.a11y.push(width);
      }
      await page.evaluate(()=>document.activeElement.blur());
      await page.screenshot({path:`${out}/private-monthly-${width}.png`,fullPage:true});
      // Public renderer always blocks private output, even a flag-only edit.
      const gate=await page.evaluate(async p=>{const m=await import('/monthly.js');m.renderReport(document.getElementById('report'),p);return document.getElementById('report').textContent;},payload);
      assert.match(gate,/월간 진단 자료 미공개/);
      for(const key of Object.keys(payload.diagnostic.axes))assert.ok(!gate.includes(String(payload.diagnostic.axes[key].value)));
      await page.evaluate(async p=>{p.publication_approved=true;p.diagnostic.publication_approved=true;const m=await import('/monthly.js');m.renderReport(document.getElementById('report'),p,'public');},payload);
      assert.equal(await page.locator('.axis').count(),0);
      // Missing values/gaps and delayed month are only mutations in browser memory.
      await page.evaluate(async p=>{p.diagnostic.axes.kto_inbound.value=null;p.history.kto_inbound[4].value=null;const m=await import('/monthly.js');m.renderReport(document.getElementById('report'),p,'private-preview');},payload);
      assert.equal(await page.locator('[data-axis="kto_inbound"] .value').textContent(),'자료 없음');
      assert.equal(await page.locator('.evidence-list li').count(),1);
      await page.evaluate(async p=>{p.history.kto_inbound[4].value=null;p.diagnostic.target_ready=false;const m=await import('/monthly.js');m.renderReport(document.getElementById('report'),p,'private-preview');},payload);
      assert.match(await page.locator('.warning').textContent(),/새 월 진단 발행 불가/);
      assert.equal(await page.locator('[data-axis="kto_inbound"] svg circle').count(),payload.history.kto_inbound.length-1);
      for(const state of ['no_data','unavailable']){
        await page.evaluate(async state=>{const m=await import('/monthly.js');m.renderReport(document.getElementById('report'),{state},'private-preview');},state);
        assert.deepEqual(await page.locator('.value').allTextContents(),['자료 없음','자료 없음']);
        assert.equal(await page.locator('svg').count(),0);assert.equal(await page.locator('.evidence-list li').count(),0);
        if(width===390)await page.screenshot({path:`${out}/${state}-${width}.png`,fullPage:true});
      }
      assert.deepEqual(errors,[]);summary.widths.push(width);await context.close();
    }
    summary.states=['verified_private','public_blocked','flag_only_blocked','missing','delayed','no_data','unavailable'];
    fs.writeFileSync(`${out}/browser-summary.json`,JSON.stringify(summary,null,2)+'\n',{mode:0o600});
    console.log('PASS: monthly local preview '+JSON.stringify(summary));
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
