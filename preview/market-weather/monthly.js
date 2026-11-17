// Private UI only. No production integration, external assets, storage, or export.
const CORES = ['kto_inbound','kto_tourism_receipts'];
const LABELS = ['방한 외래관광객','일반여행수입'];
const DEFINITIONS = ['국적별 부분집합이 아닌 방한 외래관광객 총계','명목 US$ · 국제수지 일반여행수입'];
const NS='http://www.w3.org/2000/svg';
function el(tag,attrs={},...children){
  const n=document.createElement(tag);
  for(const [k,v] of Object.entries(attrs))n.setAttribute(k,String(v));
  for(const child of children.flat())if(child!==null&&child!==undefined)n.append(child instanceof Node?child:document.createTextNode(String(child)));
  return n;
}
function svg(tag,attrs={},text){const n=document.createElementNS(NS,tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,String(v));if(text!==undefined)n.textContent=text;return n;}
function value(v){return Number.isSafeInteger(v)&&v>=0?new Intl.NumberFormat('ko-KR').format(v):'자료 없음';}
function period(p){return /^\d{4}-(0[1-9]|1[0-2])$/.test(p||'')?p.replace('-','.'):'미확인';}
function date(s){if(!s||!Number.isFinite(Date.parse(s)))return '미확인';return new Intl.DateTimeFormat('ko-KR',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(s))+' KST';}
export function formatRate(raw){
  if(typeof raw!=='string'||!/^[-+]?\d+(\.\d{1,6})?$/.test(raw))return '비교 불가';
  const negative=raw.startsWith('-'),[integer,decimal='']=raw.replace(/^[-+]/,'').split('.');
  let hundredths=BigInt(integer)*100n+BigInt(decimal.padEnd(3,'0').slice(0,2));
  if(Number(decimal.padEnd(3,'0')[2])>=5)hundredths++;
  const sign=hundredths===0n?'':negative?'-':'+';
  return sign+(hundredths/100n)+'.'+String(hundredths%100n).padStart(2,'0')+'%';
}
function link(url,label){
  try{const u=new URL(url);if(u.protocol==='https:'&&!u.username&&!u.password&&['datalab.visitkorea.or.kr','know.tour.go.kr'].includes(u.hostname))return el('a',{href:u.href,target:'_blank',rel:'noopener noreferrer'},label+' ↗');}catch{}
  return el('span',{},'공식 출처 미확인');
}
function metricRate(label,base,rate){return el('div',{},el('dt',{},label+' · '+period(base)),el('dd',{},formatRate(rate)));}
function chart(key,rows){
  const valid=rows.filter(r=>Number.isSafeInteger(r.value)&&r.value>=0);
  if(valid.length<2)return el('p',{class:'no-data'},'추이를 그릴 비교 자료가 부족합니다. 값을 보충하지 않습니다.');
  const min=Math.min(...valid.map(r=>r.value)),max=Math.max(...valid.map(r=>r.value));
  const x=i=>44+i*414/Math.max(rows.length-1,1),y=v=>max===min?80:138-(v-min)/(max-min)*106;
  const fig=el('figure',{class:'plot'}),graph=svg('svg',{viewBox:'0 0 480 180',role:'img','aria-labelledby':key+'-chart-title '+key+'-chart-desc'});
  graph.append(svg('title',{id:key+'-chart-title'},LABELS[CORES.indexOf(key)]+' 승인된 최근 월별 원값 추이'));
  graph.append(svg('desc',{id:key+'-chart-desc'},'표시 구간의 최소·최대 범위이며 0 기준 축이 아닙니다. 누락 월은 연결하지 않습니다. 아래 표에서 정확한 값을 확인할 수 있습니다.'));
  for(const v of new Set([min,max])){graph.append(svg('line',{x1:44,x2:458,y1:y(v),y2:y(v),stroke:'#d7e0ec','stroke-dasharray':'3 4'}));graph.append(svg('text',{x:44,y:y(v)-9,class:'chart-label'},value(v)));}
  let previous=null;
  rows.forEach((r,i)=>{
    if(!Number.isSafeInteger(r.value)||r.value<0){previous=null;return;}
    if(previous!==null)graph.append(svg('line',{x1:x(previous),y1:y(rows[previous].value),x2:x(i),y2:y(r.value),stroke:'#173b73','stroke-width':2}));
    graph.append(svg('circle',{cx:x(i),cy:y(r.value),r:3,fill:'#173b73','data-period':r.period}));previous=i;
    if(i===0||i===rows.length-1||i===Math.floor(rows.length/2))graph.append(svg('text',{x:x(i),y:169,'text-anchor':i===0?'start':i===rows.length-1?'end':'middle',class:'chart-label'},period(r.period)));
  });
  fig.append(graph,el('figcaption',{},'최근 승인 월별 원값 · 0 기준 축 아님 · 누락 월 연결 안 함'));
  const table=el('table',{},
    el('caption',{},'차트의 월별 원값'),
    el('thead',{},el('tr',{},el('th',{scope:'col'},'기준월'),el('th',{scope:'col'},'관측값'))),
    el('tbody',{},rows.map(r=>el('tr',{},el('th',{scope:'row'},period(r.period)),el('td',{},value(r.value))))));
  fig.append(el('details',{},el('summary',{},'월별 수치 표로 확인'),table));return fig;
}
function axis(key,index,payload){
  const row=payload.diagnostic?.axes?.[key],observed=row?.status==='observed'&&Number.isSafeInteger(row.value)&&row.value>=0;
  const comp=row?.comparisons||{},section=el('section',{class:'axis','aria-labelledby':key+'-heading','data-axis':key});
  section.append(el('div',{class:'axis-head'},el('span',{class:'number','aria-hidden':'true'},'0'+(index+1)),el('h3',{id:key+'-heading'},LABELS[index])),el('p',{class:'definition'},DEFINITIONS[index]));
  section.append(el('div',{class:'value','data-value':observed?'present':'missing'},observed?value(row.value):'자료 없음'),el('p',{class:'unit'},observed?row.unit+' · '+period(row.period)+' 기준':'미확보 · 0으로 대체하지 않음'));
  section.append(el('dl',{class:'rates'},metricRate('전년 동월',comp.yoy_base_period,observed?comp.yoy_pct:null),metricRate('전월',comp.mom_base_period,observed?comp.mom_pct:null)));
  section.append(chart(key,observed?(payload.history?.[key]||[]):[]));
  section.append(el('p',{class:'source'},link(row?.provenance?.source_url,'공식 통계 원문')));
  return section;
}
function blocked(root){root.replaceChildren(el('section',{class:'blocked',role:'status'},el('div',{class:'eyebrow'},'PUBLICATION GATE'),el('h1',{},'월간 진단 자료 미공개'),el('p',{},'공개 승인과 편집 검수 전에는 수치와 비공개 초안을 표시하지 않습니다.')));}
export function renderReport(root,payload={},context='public'){
  // Public integration is deliberately closed in Step 14, including flag-only edits.
  if(context!=='private-preview'){blocked(root);return;}
  if(payload.state!=='private_review')payload={state:payload.state};
  const diagnostic=payload.diagnostic||{},ready=payload.state==='private_review'&&diagnostic.target_ready===true;
  const target=period(diagnostic.target_period),meta=el('dl',{class:'metadata'});
  for(const [k,v] of [['발행월','미정 · 미발행'],['통계 기준월',target],['자료 마감',date(diagnostic.input_cutoff)],['분석 방식','현재 빈티지 회고']])meta.append(el('div',{},el('dt',{},k),el('dd',{},v)));
  const hero=el('header',{class:'hero'},el('div',{class:'eyebrow'},'MONTHLY / TOURISM MARKET MONITOR'),el('h1',{},'Market Weather'),el('p',{class:'deck'},'방한 수요와 일반여행수입으로 읽는 월간 관광 흐름.'),meta);
  const status=el('section',{class:'status','aria-labelledby':'overall-heading'},el('div',{},el('div',{class:'eyebrow'},'OVERALL ASSESSMENT'),el('h2',{id:'overall-heading'},'종합 판정 보류')),el('p',{},el('strong',{},ready?'두 핵심 지표의 부분 모니터입니다.':'검토 가능한 목표월 자료가 부족합니다.'),el('br'),'산업 활동 입력이 없어 관광시장 전체 상태를 판정하지 않습니다. 점수와 날씨 등급을 산출하지 않습니다.'));
  const axes=el('div',{class:'axes'},CORES.map((k,i)=>axis(k,i,payload)));
  const evidence=el('section',{'aria-labelledby':'evidence-heading'},el('div',{class:'section-top'},el('h2',{id:'evidence-heading'},'관측의 주요 근거'),el('span',{},'원지표와 비교월에 한정한 사실')));
  const reasons=(payload.briefing?.evidence||[]).filter(e=>CORES.includes(e.indicator)&&Number.isSafeInteger(diagnostic.axes?.[e.indicator]?.value)).slice(0,3);
  if(reasons.length)evidence.append(el('ol',{class:'evidence-list'},reasons.map(e=>el('li',{},el('div',{},el('p',{},e.text),link(e.source?.source_url,e.source?.publisher||'공식 출처'))))));
  else evidence.append(el('p',{class:'no-data'},'확보된 근거가 없습니다. 예시 문장을 생성하지 않습니다.'));
  const notes=el('aside',{class:'notes','aria-labelledby':'notes-heading'},el('h2',{id:'notes-heading'},'통계를 읽기 전에'),el('ul',{},[
    '방한객은 인원 통계, 수입은 명목 US$ 국제수지 통계로 모집단이 다릅니다.',
    'MoM은 비계절조정 원계열 비교입니다. 계절 변화와 공표 시차를 함께 확인해야 합니다.',
    '팬데믹 회복기의 기저효과로 YoY가 커질 수 있으며, 증가를 호황으로 판정하지 않습니다.',
    '기준월 또는 비교월의 정정으로 수치와 변화율이 달라질 수 있습니다.',
    '과거 당시 빈티지가 입증되지 않아 실시간 백테스트로 해석할 수 없습니다.'
  ].map(t=>el('li',{},t))));
  const archive=el('section',{class:'archive','aria-labelledby':'archive-heading'},el('div',{class:'section-top'},el('h2',{id:'archive-heading'},'발행 기록과 방법론'),el('span',{},'검토 중인 정보 구조 · 공개 아카이브 아님')));
  const lineage=el('details',{},el('summary',{},'검토본 추적 정보'),el('p',{},'편집 검토: 대기 · 게시 승인: false'),el('p',{},'분석 실행: '+date(diagnostic.analysis_at)),el('p',{},'모형: ',el('code',{},payload.methodology_version||'미확인')),el('p',{},'입력 원장 해시: ',el('code',{},diagnostic.input_hashes?.archive||'미확인')));
  archive.append(el('div',{class:'archive-grid'},el('div',{},el('h3',{},'과거 발행물'),el('p',{},'공개 발행물 없음. 비공개 검토본을 발행 이력으로 노출하지 않습니다.')),el('div',{},el('h3',{},'방법론 v0.1'),el('p',{},'동일 기준월의 두 핵심을 정렬하고 정확한 원값으로 MoM·YoY를 비교합니다.'),lineage),el('div',{},el('h3',{},'정정·검토 이력'),el('p',{},'이전 입력과 검토본은 덮어쓰지 않고 해시로 연결합니다.'),el('p',{},'기록된 검토본 연결: '+(Number.isInteger(payload.revision_count)?payload.revision_count+'건':'미확인')+' · 공식 통계 정정 건수와 다름'))));
  archive.append(el('p',{class:'context',id:'context'},'Macro Monitor는 개별 공식 통계, Daily Briefing은 일간 뉴스 맥락을 제공합니다. 이 Preview는 월간 해석의 비공개 검토용이며 기존 사이트로 자동 연결하거나 발행하지 않습니다.'));
  root.replaceChildren(hero,status);
  if(!ready)root.append(el('p',{class:'warning',role:'status'},payload.state==='unavailable'?'자료 검증 또는 접근에 실패했습니다. 통계는 표시하지 않습니다.':'목표월 자료 없음 또는 갱신 지연 · 새 월 진단 발행 불가'));
  const warnings=[...(diagnostic.warnings||[]),...CORES.flatMap(k=>diagnostic.axes?.[k]?.warnings||[])].filter(w=>w!=='industry_activity_unavailable');
  const warningText={target_period_unavailable_or_delayed:'목표 기준월 미확보 또는 갱신 지연',comparative_judgment_withheld:'비교 기준이 부족하여 증감 판단 보류',yoy_unavailable_or_zero_baseline:'전년값 없음 또는 0으로 YoY 비교 불가',mom_unavailable_or_zero_baseline:'전월값 없음 또는 0으로 MoM 비교 불가',pandemic_baseline_context_required:'팬데믹 시기의 비교 기준으로 기저효과 검토 필요',revised_observation:'현재 관측에 정정 이력 있음',revised_comparison_baseline:'비교 기준월에 정정 이력 있음'};
  if(warnings.length)root.append(el('details',{},el('summary',{},'자료 상태·정정 경고 확인'),el('ul',{},[...new Set(warnings.map(w=>warningText[w]||'사용 자격을 확인하지 못한 통계 제외'))].map(w=>el('li',{},w)))));
  root.append(el('div',{class:'section-top'},el('h2',{},'두 가지 월간 흐름'),el('span',{},'승인된 핵심 지표만 사용 · 미확보 값 보충 없음')),axes,el('div',{class:'reading'},evidence,notes),archive);
}
async function boot(){
  const root=document.getElementById('report');if(!root)return;
  if(location.hostname!=='127.0.0.1'){blocked(root);return;}
  try{const r=await fetch('/api/preview',{credentials:'same-origin',cache:'no-store'});if(!r.ok)throw Error('unavailable');renderReport(root,await r.json(),'private-preview');}
  catch{renderReport(root,{state:'unavailable'},'private-preview');}
}
boot();
