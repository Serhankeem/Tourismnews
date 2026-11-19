// Shared presentation only: caller must enforce publication or private-session access.
const core=['kto_inbound','kto_tourism_receipts'];
const url=s=>{try{const u=new URL(s);return u.protocol==='https:'&&!u.username&&!u.password&&['datalab.visitkorea.or.kr','know.tour.go.kr'].includes(u.hostname);}catch{return false;}};
 function el(tag,attrs={},...children){const n=document.createElement(tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,v);for(const c of children.flat())n.append(c instanceof Node?c:document.createTextNode(String(c)));return n;}
 function inline(parent,raw){for(const s of raw.split(/(\*\*[^*]+\*\*|\*[^*\n]+\*|\[[^\]]+\]\(https:\/\/[^\s)]+\))/g)){
  const m=s.match(/^\[([^\]]+)\]\((https:\/\/[^\s)]+)\)$/);
  if(m&&url(m[2]))parent.append(el('a',{href:m[2],target:'_blank',rel:'noopener noreferrer'},m[1]+' ↗'));
  else if(s.startsWith('**'))parent.append(el('strong',{},s.slice(2,-2)));
  else if(s.startsWith('*'))parent.append(el('em',{},s.slice(1,-1)));
  else parent.append(document.createTextNode(s));
 }return parent;}
 function rate(raw){if(raw===null)return '비교 불가';const negative=raw.startsWith('-');const [a,b]=raw.replace('-','').split('.');let n=BigInt(a)*100n+BigInt(b.slice(0,2));if(Number(b[2])>=5)n++;return (n===0n?'':negative?'-':'+')+(n/100n)+'.'+String(n%100n).padStart(2,'0')+'%';}

export function edition(article,reference){
 const blocks=article.sections[0].markdown.split('\n\n');
 if(blocks[0]!=='한국 관광의 날씨는? / MONTHLY REPORT')return null;
 const series=blocks[1]?.match(/^(\d{4})년 (\d{1,2})월 Market Weather$/);
 const [y,m]=String(reference).split('-').map(Number);
 if(!series||Number(series[2])<1||Number(series[2])>12||blocks[2]!==`${y}년 ${m}월 검증 자료 기반`||blocks[3]!==`${series[1]}.${series[2].padStart(2,'0')} · VOL. 01`||blocks[4]!==`발행: ${series[1]}년 ${Number(series[2])}월\n통계 기준: ${y}년 ${m}월`||typeof blocks[5]!=='string'||blocks[5].length===0||blocks.length<7)return null;
 return {brand:blocks[0],series:blocks[1],description:blocks[2],issue:blocks[3],metadata:blocks[4],lead:blocks[5],body:blocks.slice(6).join('\n\n')};
}
export function renderArticle(root,p,heading='h3'){
 root.replaceChildren();const sectionHeading=heading==='h1'?'h2':'h4';const cover=edition(p.article,p.reference_period);
 if(cover)root.append(el('p',{class:'monthly-brand'},cover.brand),el('p',{class:'monthly-series'},cover.series),el('p',{class:'monthly-description'},cover.description),el('p',{class:'monthly-issue'},cover.issue));
  root.append(el(heading,{class:'monthly-title',tabindex:'-1'},p.title),el('p',{class:'monthly-subtitle'},p.article.subtitle),el('p',{class:'monthly-notice'},'산업 활동 입력 부족 · 관광시장 전체 종합 판정 보류'));
  const data=el('div',{class:'monthly-metrics'});
  for(const [i,k] of core.entries()){const m=p.metrics[k];data.append(el('section',{},el(sectionHeading,{},i===0?'방한 외래관광객':'일반여행수입'),el('p',{class:'monthly-value'},new Intl.NumberFormat('ko-KR').format(m.value)+' '+m.unit),el('p',{},'전년 동월 '+m.comparisons.yoy.period+' 대비 '+rate(m.comparisons.yoy.pct)),el('p',{},'전월 '+m.comparisons.mom.period+' 대비 '+rate(m.comparisons.mom.pct))));}
  root.append(data);
  if(cover)root.insertBefore(el('p',{class:'monthly-edition-metadata'},cover.metadata),root.querySelector('.monthly-notice'));
  if(cover)root.insertBefore(el('p',{class:'monthly-lead'},cover.lead),root.querySelector('.monthly-notice'));
  for(const [index,original] of p.article.sections.entries()){const s=index===0&&cover?{...original,markdown:cover.body}:original;const section=el('section',{},el(sectionHeading,{},s.heading));for(const block of s.markdown.split('\n\n'))section.append(block.startsWith('- ')?el('ul',{},block.split('\n').map(line=>inline(el('li'),line.replace(/^- /,'')))):inline(el('p'),block));root.append(section);}
  root.append(el('p',{class:'tiny'},'자료 마감 '+new Date(p.data_cutoff).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'})+' KST · 현재 빈티지 회고 분석'),el('a',{href:'#macro',class:'text-link'},'Macro Monitor 상세 통계 →'));
}
