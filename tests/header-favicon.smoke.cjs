// Header-only behavior regression; real approved public data stays read-only.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const nav=require('./navigation-helper.cjs');
const base=(process.env.TOURISM_TEST_URL||'http://127.0.0.1:8074/tourismnews').replace(/\/$/,'');
const out=process.env.HEADER_FAVICON_OUTPUT||'/tmp/currentourism-header-favicon';
const names=['favicon.ico','favicon-32x32.png','apple-touch-icon.png','icon-192.png','icon-512.png'];

async function active(page,route){
 const weather=['weather','weather-simulator'].includes(route),news=['news','briefing','research'].includes(route);
 const button=page.locator('#weather-menu-toggle');
 assert.equal(await button.evaluate(e=>e.classList.contains('active')),weather);
 assert.equal(await button.getAttribute('aria-current'),weather?'true':null);
 assert.equal(await page.locator('#news-menu-toggle').getAttribute('aria-current'),news?'true':null);
 const macro=page.locator('.primary-navigation>a[data-nav="macro"]');
 assert.equal(await macro.getAttribute('aria-current'),route==='macro'?'page':null);
 assert.equal(await macro.evaluate(e=>e.classList.contains('active')),route==='macro');
 const top=await page.locator('.primary-navigation>a.active,.primary-navigation>[data-header-disclosure]>button.active').count();
 assert.equal(top,route==='overview'?0:1);
 for(const href of await page.locator('.primary-navigation a[aria-current="page"]').evaluateAll(es=>es.map(e=>e.getAttribute('href'))))assert.equal(href,'#'+route);
 if(['weather','weather-simulator','macro'].includes(route))assert.equal(await page.locator('#weather-submenu [aria-current="page"]').getAttribute('href'),'#'+route);
}

async function scanHeader(page){
 if(!process.env.AXE_PATH)return;
 await page.addScriptTag({path:process.env.AXE_PATH});
 const failures=await page.evaluate(async()=>{
  const result=await axe.run(document.querySelector('.site-header'),{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}});
  return result.violations.map(v=>({id:v.id,targets:v.nodes.map(n=>n.target)}));
 });assert.deepEqual(failures,[]);
}

(async()=>{fs.mkdirSync(out,{recursive:true});const browser=await chromium.launch({headless:true});
try{for(const width of [320,390,768,1440]){
 const page=await browser.newPage({viewport:{width,height:1100},isMobile:width<=390,hasTouch:width<=768}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/#macro');
 await page.waitForFunction(()=>MacroMonitor?.database&&document.querySelector('.site-header').hasAttribute('data-compact'));
 await active(page,'macro');
 const menu=page.locator('#header-menu-toggle'),weather=page.locator('#weather-menu-toggle');
 const compact=await menu.isVisible();
 if(compact){await menu.focus();await page.keyboard.press('Enter');}
 await weather.focus();await page.keyboard.press('Space');
 assert.equal(await weather.getAttribute('aria-expanded'),'true');await active(page,'macro');
 // The expanded background must not confer the active orange route underline.
 assert.equal(await weather.evaluate(e=>getComputedStyle(e).borderBottomColor),'rgba(0, 0, 0, 0)');
 assert.equal(await page.locator('.primary-navigation>a[data-nav="macro"]').evaluate(e=>getComputedStyle(e).borderBottomColor),'rgb(244, 119, 53)');
 await page.keyboard.press('Tab');assert.ok(await page.locator('#weather-submenu a').first().evaluate(e=>e===document.activeElement));
 await page.keyboard.press('Escape');assert.equal(await weather.getAttribute('aria-expanded'),'false');
 assert.ok(await weather.evaluate(e=>e===document.activeElement));await active(page,'macro');
 await weather.focus();await page.keyboard.press('Enter');assert.equal(await weather.getAttribute('aria-expanded'),'true');
 await scanHeader(page);
 if([390,1440].includes(width))await page.screenshot({path:`${out}/macro-menu-open-${width}.png`});
 const box=await page.locator('.site-header').boundingBox(),navBox=await page.locator('#primary-navigation').boundingBox();
 await page.mouse.click(width-8,Math.min(1090,Math.max(box.y+box.height,navBox.y+navBox.height)+80));
 assert.equal(await weather.getAttribute('aria-expanded'),'false');
 if(compact)assert.equal(await menu.getAttribute('aria-expanded'),'false');
 for(const route of ['weather','weather-simulator','macro','news','briefing','research','about']){
  await nav(page,route);await active(page,route);
  assert.equal(await weather.getAttribute('aria-expanded'),'false');
  await page.reload();await active(page,route);
 }
 await nav(page,'weather');await nav(page,'weather-simulator');await nav(page,'macro');
 await page.goBack();await active(page,'weather-simulator');await page.goForward();await active(page,'macro');
 for(const route of ['macro','weather','weather-simulator']){
  await page.goto(base+'/#'+route);await page.reload();await active(page,route);
  if([390,1440].includes(width))await page.screenshot({path:`${out}/${route}-${width}.png`});
 }
 const icons=await page.locator('head link[rel="icon"],head link[rel="apple-touch-icon"]').evaluateAll(es=>es.map(e=>({href:e.getAttribute('href'),url:e.href,rel:e.rel,sizes:e.getAttribute('sizes')})));
 assert.equal(icons.length,5);
 for(const name of names){
  const icon=icons.find(i=>i.href==='./assets/'+name);assert.ok(icon);
  assert.equal(new URL(icon.url).pathname,new URL(base+'/assets/'+name).pathname);
  const response=await page.request.get(icon.url);assert.ok(response.ok());assert.ok((await response.body()).length>0);
 }
 const dimensions=await page.evaluate(async urls=>Promise.all(urls.map(url=>new Promise((resolve,reject)=>{
  const i=new Image();i.onload=()=>resolve([i.naturalWidth,i.naturalHeight]);i.onerror=()=>reject(Error('icon_decode_failed'));i.src=url;
 }))),icons.filter(i=>i.href.endsWith('.png')).map(i=>i.url));
 assert.deepEqual(dimensions,[[32,32],[192,192],[512,512],[180,180]]);
 assert.match(await page.locator('#brand-logo').getAttribute('src'),/^\.\/assets\/currentourism-new-airplane-logo\.png\?/);
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);
 await page.close();
}console.log('PASS header/favicon: 4 widths; exclusive macro/weather/news/about active routes; expansion independent; native keys/focus/outside click; direct/reload/history; 5 original icons load/decode under Pages prefix; original logo retained; header axe if configured');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
