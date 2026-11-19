import {renderArticle,edition} from './monthly-market-weather-view.js';
/* Public minimal-contract reader only. Never fetches private drafts or approvals.
 * Authentication is enforced by the producer/Pages gate, not these client checks.
 */
(() => {
 const get=id=>document.getElementById(id),core=['kto_inbound','kto_tourism_receipts'];let cached=null,loading=false;
 const fields=['schema_version','content_id','revision','editorial_revision','reference_period','issued_at','data_cutoff','analysis_mode','title','summary','overall_state','metrics','evidence','sources','limitations','methodology_version','correction','article'];
 const exact=(o,keys)=>o&&typeof o==='object'&&!Array.isArray(o)&&Object.keys(o).sort().join('|')===[...keys].sort().join('|');
 const month=s=>typeof s==='string'&&/^\d{4}-(0[1-9]|1[0-2])$/.test(s);
 const text=(s,n=6000)=>typeof s==='string'&&s.length>0&&s.length<=n;
 const date=s=>typeof s==='string'&&Number.isFinite(Date.parse(s));
 const url=s=>{try{const u=new URL(s);return u.protocol==='https:'&&!u.username&&!u.password&&['datalab.visitkorea.or.kr','know.tour.go.kr'].includes(u.hostname);}catch{return false;}};
 function valid(p){
  if(!exact(p,fields)||p.schema_version!==2||p.overall_state!=='withheld'||p.analysis_mode!=='retrospective_current_vintage'||p.revision!==1||p.correction!==null||!/^r[1-9]\d*$/.test(p.editorial_revision)||!month(p.reference_period)||p.content_id!=='market-weather-'+p.reference_period||!date(p.issued_at)||!date(p.data_cutoff)||!text(p.title,600)||!text(p.summary)||!/^weather-diagnostic-v\d+\.\d+(\.\d+)?$/.test(p.methodology_version))return false;
  if(!exact(p.metrics,core)||!exact(p.article,['subtitle','sections'])||!text(p.article.subtitle,600)||!Array.isArray(p.article.sections)||p.article.sections.length!==5||!p.article.sections.every(s=>exact(s,['heading','markdown'])&&text(s.heading,600)&&text(s.markdown)))return false;
  for(const [i,k] of core.entries()){
   const m=p.metrics[k];if(!exact(m,['value','unit','comparisons'])||!Number.isSafeInteger(m.value)||m.value<0||m.unit!==(i===0?'명':'US$')||!exact(m.comparisons,['mom','yoy']))return false;
   for(const r of Object.values(m.comparisons))if(!exact(r,['period','pct','direction'])||!month(r.period)||(r.pct!==null&&(typeof r.pct!=='string'||!/^[-]?\d+\.\d{6}$/.test(r.pct)))||!['increase','decrease','unchanged','unavailable'].includes(r.direction))return false;
  }
  if(!Array.isArray(p.sources)||p.sources.length!==2||!p.sources.every(s=>exact(s,['id','publisher','url','original_publication_at','finality'])&&text(s.id,40)&&text(s.publisher,600)&&url(s.url)&&(s.original_publication_at===null||date(s.original_publication_at))&&['not_stated','provisional','final'].includes(s.finality))||new Set(p.sources.map(s=>s.id)).size!==2)return false;
  if(!Array.isArray(p.evidence)||p.evidence.length<1||p.evidence.length>3||!p.evidence.every(e=>exact(e,['indicator','text','source_ids','comparison_periods'])&&core.includes(e.indicator)&&text(e.text)&&Array.isArray(e.source_ids)&&e.source_ids.length>0&&e.source_ids.every(id=>p.sources.some(s=>s.id===id))&&Array.isArray(e.comparison_periods)&&e.comparison_periods.length>0&&e.comparison_periods.length<=2&&e.comparison_periods.every(month)))return false;
  return exact(p.limitations,['industry_activity_missing','nominal_bop_definition','nonseasonal_mom','vintage_and_lag','base_effect_and_revisions'])&&Object.values(p.limitations).every(s=>text(s));
 }
 function canonical(v){if(Array.isArray(v))return '['+v.map(canonical).join(',')+']';if(v&&typeof v==='object')return '{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}';return JSON.stringify(v);}
 async function digest(p){const raw=new TextEncoder().encode(canonical(p));return [...new Uint8Array(await crypto.subtle.digest('SHA-256',raw))].map(b=>b.toString(16).padStart(2,'0')).join('');}
 function clear(){get('monthly-state').textContent='아직 발행된 월간 진단 없음';get('monthly-article').replaceChildren();get('monthly-picker').hidden=true;cached=null;}
 function render(k){
  const p=cached.archive.contents[k],entry=cached.index.entries.find(e=>e.key===k);
  if(!entry||Date.parse(entry.not_after)<Date.now()){clear();return;}
  const root=get('monthly-article');root.replaceChildren();get('monthly-state').textContent='통계 기준월 '+p.reference_period+' · 편집 '+p.editorial_revision+' · 공개 판본 '+p.revision;
  renderArticle(root,p);
 }
 async function load(){
  if(loading)return;if(cached){render(get('monthly-edition').value||cached.index.latest);return;}
  loading=true;
  try{
   const r=await Promise.all(['market_weather_index.json','market_weather_archive.json'].map(n=>fetch('./data/'+n,{cache:'no-store'})));if(!r.every(x=>x.ok))throw Error('unpublished');
   const [index,archive]=await Promise.all(r.map(x=>x.json()));
   if(!exact(index,['schema_version','kind','latest','entries'])||index.schema_version!==1||index.kind!=='approved_market_weather_index'||!Array.isArray(index.entries)||!index.entries.length||!exact(archive,['schema_version','kind','contents'])||archive.schema_version!==1||archive.kind!=='approved_market_weather_archive')throw Error('invalid');
   const keys=new Set();for(const e of index.entries){const p=archive.contents?.[e.key];if(!exact(e,['key','content_id','revision','editorial_revision','reference_period','title','issued_at','not_after','content_sha256'])||keys.has(e.key)||!valid(p)||e.key!==p.content_id+':'+p.revision||e.content_id!==p.content_id||e.revision!==p.revision||e.editorial_revision!==p.editorial_revision||e.reference_period!==p.reference_period||e.title!==p.title||e.issued_at!==p.issued_at||!date(e.not_after)||Date.parse(e.not_after)<Date.now()||Date.parse(e.issued_at)>Date.now()||await digest(p)!==e.content_sha256)throw Error('invalid');keys.add(e.key);}
   if(keys.size!==Object.keys(archive.contents).length||!keys.has(index.latest)||index.latest!==index.entries[0].key)throw Error('invalid');
   cached={index,archive};const select=get('monthly-edition');select.replaceChildren(...index.entries.map(e=>{const cover=edition(archive.contents[e.key].article,e.reference_period);return new Option((cover?cover.issue+' · 통계 ':'통계 ')+e.reference_period+' · 공개 판본 '+e.revision,e.key);}));select.value=index.latest;get('monthly-picker').hidden=false;render(index.latest);
  }catch{clear();}finally{loading=false;}
 }
 get('monthly-edition')?.addEventListener('change',()=>{render(get('monthly-edition').value);get('monthly-article').querySelector('.monthly-title')?.focus();});
 window.MonthlyWeather={load,clear};if(!get('page-weather')?.classList.contains('hide-section')&&!get('weather-monthly').hidden)load();
})();
