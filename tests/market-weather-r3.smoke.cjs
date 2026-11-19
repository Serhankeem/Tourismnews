// Actual draft via loopback/session API only. Screenshots must stay outside Git.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const base=process.env.R3_PREVIEW_URL||'http://127.0.0.1:8070',out=path.resolve(process.env.R3_OUTPUT||'/tmp/weather-r3-private');
assert.ok(!out.startsWith(path.resolve(__dirname,'..')+path.sep));fs.mkdirSync(out,{recursive:true,mode:0o700});
(async()=>{const browser=await chromium.launch({headless:true});try{
 for(const width of [320,390,768,1440]){
  const context=await browser.newContext({viewport:{width,height:1100},reducedMotion:'reduce'}),page=await context.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));await page.goto(base);await page.locator('.monthly-title').waitFor();
  const p=await page.evaluate(async()=>await(await fetch('/api/preview')).json());
  assert.equal(p.pending_editorial.editorial_status,'pending');assert.equal(p.pending_editorial.publication_status,'not_requested');assert.equal(p.pending_editorial.actual_publication_date,null);
  if(process.env.R3_EXPECTED_SHA256)assert.equal(p.pending_editorial.manuscript_sha256,process.env.R3_EXPECTED_SHA256);
  assert.equal(await page.locator('h1').textContent(),'2026년 11월 관광시장 진단');
  assert.equal(await page.locator('.monthly-brand').textContent(),'한국 관광의 날씨는? / MONTHLY REPORT');
  assert.equal(await page.locator('.monthly-series').textContent(),'2026년 11월 Market Weather');
  assert.equal(await page.locator('.monthly-description').textContent(),'2026년 9월 검증 자료 기반');
  assert.equal(await page.locator('.monthly-issue').textContent(),'2026.11 · VOL. 01');
  assert.equal(await page.locator('.monthly-edition-metadata').textContent(),`${process.env.R3_ISSUE_LABEL||'발행'}: 2026년 11월\n통계 기준: 2026년 9월`);
  assert.equal(await page.locator('#monthly-article>section').count(),5);assert.equal(await page.locator('.axis').count(),2);
  assert.match(await page.locator('#publication-gate-status').textContent(),/승인 대기.*미요청.*미발행.*미정/);
  for(const [index,key] of ['kto_inbound','kto_tourism_receipts'].entries()){
   const row=p.diagnostic.axes[key],axis=page.locator(`[data-axis="${key}"]`);
   assert.ok((await page.locator('.monthly-value').nth(index).textContent()).includes(new Intl.NumberFormat('ko-KR').format(row.value)));
   assert.equal(await axis.locator('.value').textContent(),new Intl.NumberFormat('ko-KR').format(row.value));
   assert.equal(p.history[key].find(r=>r.period===row.period).value,row.value);
   assert.equal(await axis.locator('svg circle').count(),p.history[key].filter(r=>r.value!==null).length);
   for(const circle of await axis.locator('svg circle').all()){const period=await circle.getAttribute('data-period');assert.ok(p.history[key].some(r=>r.period===period&&Number.isSafeInteger(r.value)));}
   assert.equal(await page.locator('#monthly-article a[href^="https:"]').nth(index).getAttribute('href'),row.provenance.source_url);
   assert.equal(await page.locator('#monthly-article a[href^="https:"]').nth(index).getAttribute('target'),'_blank');
   assert.match(await page.locator('#monthly-article a[href^="https:"]').nth(index).getAttribute('rel'),/noopener noreferrer/);
  }
  assert.match(await page.locator('#monthly-article').textContent(),/종합 판정.*보류/);
  assert.match(await page.locator('#monthly-article').textContent(),/잠정·확정 여부.*확인되지 않았다/);
  assert.match(await page.locator('#monthly-article').textContent(),/2026년 11월 17일 오전 10시 50분/);
  await page.keyboard.press('Tab');assert.ok(await page.locator('.skip').evaluate(n=>n===document.activeElement));await page.keyboard.press('Enter');
  await page.locator('.plot summary').first().focus();await page.keyboard.press('Enter');assert.equal(await page.locator('.plot details').first().evaluate(n=>n.open),true);
  if(process.env.AXE_PATH){await page.route('**/axe-test-only.js',r=>r.fulfill({contentType:'text/javascript',body:fs.readFileSync(process.env.AXE_PATH,'utf8')}));await page.addScriptTag({url:base+'/axe-test-only.js'});const v=await page.evaluate(async()=>{const r=await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}});return r.violations.map(x=>({id:x.id,nodes:x.nodes.map(n=>n.target)}));});assert.deepEqual(v,[]);}
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  assert.deepEqual(await page.locator('#monthly-article>*').evaluateAll(nodes=>nodes.flatMap((n,i)=>{
   const r=n.getBoundingClientRect(),previous=i?nodes[i-1].getBoundingClientRect():null;
   return r.x<0||r.right>innerWidth+1||n.scrollWidth>n.clientWidth+1||(previous&&r.top<previous.bottom-1)?[n.className||n.tagName]:[];
  })),[],'No clipped text, horizontal overflow or overlapping article blocks');
  await page.screenshot({path:out+'/r3-'+width+'.png',fullPage:true});
  for(const route of ['/api/public','/manuscript-r3.md','/review-manifest.json','/data/market_weather_archive.json'])assert.equal((await page.request.get(base+route)).status(),404);
  await page.evaluate(async p=>{p.publication_approved=true;const m=await import('/monthly.js');m.renderReport(document.getElementById('report'),p,'public');},p);assert.equal(await page.locator('.monthly-title,.axis').count(),0);
  assert.deepEqual(errors,[]);await context.close();
 }
 const fresh=await browser.newContext();assert.equal((await fresh.request.get(base+'/api/preview')).status(),403);await fresh.close();
 console.log('PASS r3: exact edition/month/title/full five sections/source links; body/chart inputs match; pending/nonpublication/null publication date; four widths/keyboard/axe; flag-only public rendering blocked and draft/public URLs unavailable');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
