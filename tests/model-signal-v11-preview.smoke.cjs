'use strict';
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const base=process.env.MODEL_V11_PREVIEW_URL||'http://127.0.0.1:8084',out=process.env.MODEL_V11_SCREENSHOTS||'/tmp/model-signal-v11-preview';
(async()=>{fs.mkdirSync(out,{recursive:true});const browser=await chromium.launch({headless:true});try{
 for(const width of [320,390,768,1440]){
  const page=await browser.newPage({viewport:{width,height:1000},bypassCSP:!!process.env.AXE_PATH}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/');await page.waitForFunction(()=>!document.getElementById('score').textContent.includes('자료 확인 중'));
  const result=await page.evaluate(()=>fetch('/result.json').then(r=>r.json()));
  assert.equal(result.publication_approved,false);assert.ok(await page.getByText('비공개 Preview',{exact:false}).isVisible());
  if(result.status==='observed'){
   assert.match(await page.locator('#score').textContent(),new RegExp(result.score_display));
   assert.ok((await page.locator('#alignment').textContent()).includes(result.reference_period));
   assert.equal(await page.locator('#axes a').count(),2);
   for(const a of result.axes){assert.ok((await page.locator('#axes').textContent()).includes(a.value.toLocaleString('ko-KR')));assert.ok(await page.locator(`#axes a[href="${a.source_url}"]`).count());}
   for(const p of Object.values(result.latest_observation_periods))assert.ok((await page.locator('#latest').textContent()).includes(p));
  }else{assert.equal(await page.locator('#score').textContent(),'모델 판정 유보');assert.ok((await page.locator('#alignment').textContent()).includes(result.reason));assert.equal(await page.locator('#axes a').count(),0);}
  await page.keyboard.press('Tab');assert.equal(await page.evaluate(()=>document.activeElement.getAttribute('href')),'#signal');
  if(process.env.AXE_PATH){await page.addScriptTag({path:process.env.AXE_PATH});const violations=await page.evaluate(async()=>(await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}})).violations.map(v=>v.id));assert.deepEqual(violations,[]);}
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);
  await page.locator('h1').click();
  if([390,1440].includes(width))await page.screenshot({path:`${out}/preview-${result.status}-${width}.png`,fullPage:true});
  await page.close();
 }
 console.log('PASS private v1.1 preview: 320/390/768/1440; exact result, common/latest months, evidence, withheld reason, keyboard, no overflow, axe if configured');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
