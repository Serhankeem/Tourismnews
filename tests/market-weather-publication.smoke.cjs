// Real editorial-only private Preview. No publication receipt or public JSON.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const base=process.env.GATE_PREVIEW_URL||'http://127.0.0.1:8050';
const out=path.resolve(process.env.GATE_SCREENSHOTS||'/tmp/weather-publication-private');
assert.ok(!out.startsWith(path.resolve(__dirname,'..')+path.sep));fs.mkdirSync(out,{recursive:true,mode:0o700});
(async()=>{
 const browser=await chromium.launch({headless:true}),summary={widths:[],axe:[],publication:'missing',public_json_generated:false};
 try{
  for(const width of [320,390,768,1440]){
   const context=await browser.newContext({viewport:{width,height:1100},reducedMotion:'reduce'}),page=await context.newPage(),errors=[];
   page.on('pageerror',e=>errors.push(e.message));await page.goto(base);await page.locator('.approved-article').waitFor();
   const payload=await page.evaluate(async()=>await(await fetch('/api/preview')).json());
   assert.equal(payload.editorial_private.gate.editorial_verified,true);assert.equal(payload.editorial_private.gate.publication_verified,false);
   assert.equal(payload.editorial_private.gate.reason,'publication_approval_missing');assert.equal(payload.publication_approved,false);
   assert.equal(await page.locator('main h1').textContent(),payload.editorial_private.article.title);
   assert.deepEqual(await page.locator('.approved-article h2').allTextContents(),payload.editorial_private.article.sections.map(s=>s.heading));
   assert.equal(await page.locator('.axis').count(),2);assert.match(await page.locator('#publication-gate-status').textContent(),/게시 승인 없음/);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
   const headings=await page.locator('.approved-article h2').all();
   for(const heading of headings)assert.equal(await heading.isVisible(),true);
   await page.keyboard.press('Tab');assert.equal(await page.evaluate(()=>document.activeElement.className),'skip');
   await page.keyboard.press('Enter');assert.equal(await page.evaluate(()=>document.activeElement.id),'report');
   const summaryNode=page.locator('.plot summary').first();await summaryNode.focus();await page.keyboard.press('Enter');
   assert.equal(await summaryNode.evaluate(n=>n.parentElement.open),true);await page.keyboard.press('Enter');
   if(process.env.GATE_AXE_SOURCE){
    await page.route('**/axe-test-only.js',r=>r.fulfill({contentType:'text/javascript',body:fs.readFileSync(process.env.GATE_AXE_SOURCE,'utf8')}));
    await page.addScriptTag({url:base+'/axe-test-only.js'});
    const violations=await page.evaluate(async()=>{const r=await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}});return r.violations.map(v=>({id:v.id,targets:v.nodes.map(n=>n.target)}));});
    assert.deepEqual(violations,[]);summary.axe.push(width);
   }
   await page.evaluate(()=>document.activeElement.blur());await page.screenshot({path:`${out}/editorial-only-r2-${width}.png`,fullPage:true});
   assert.equal((await page.request.get(base+'/api/public')).status(),404);
   await page.evaluate(async payload=>{payload.publication_approved=true;payload.editorial_private.gate.publication_verified=true;const {renderReport}=await import('/monthly.js');renderReport(document.getElementById('report'),payload,'public');},payload);
   assert.equal(await page.locator('.approved-article,.axis').count(),0);assert.match(await page.locator('main').textContent(),/월간 진단 자료 미공개/);
   if(width===390)await page.screenshot({path:`${out}/public-blocked-390.png`,fullPage:true});
   assert.deepEqual(errors,[]);summary.widths.push(width);await context.close();
  }
  const fresh=await browser.newContext();assert.equal((await fresh.request.get(base+'/api/preview')).status(),403);await fresh.close();
  fs.writeFileSync(`${out}/browser-summary.json`,JSON.stringify(summary,null,2)+'\n',{mode:0o600});
  console.log('PASS: editorial-only full r2 Preview, 5 sections, 4 widths, keyboard/axe, publication missing, public renderer and HTTP gate closed');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
