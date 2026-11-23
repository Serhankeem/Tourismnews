/* Pure, deterministic current-vintage research model. No fetch, DOM or writes. */
(function(root,factory){if(typeof module==='object'&&module.exports)module.exports=factory(require('./market-signal-registry.js'));else root.MarketSignalModel=factory(root.MarketSignalRegistry);})(globalThis,registry=>{
 'use strict';
 const month=p=>typeof p==='string'&&/^(19|20)\d\d-(0[1-9]|1[0-2])$/.test(p);
 const add=(p,n)=>{const [y,m]=p.split('-').map(Number),d=new Date(Date.UTC(y,m-1+n,1));return d.getUTCFullYear()+'-'+String(d.getUTCMonth()+1).padStart(2,'0');};
 const distance=(a,b)=>(Number(a.slice(0,4))-Number(b.slice(0,4)))*12+Number(a.slice(5))-Number(b.slice(5));
 const need=(ok,code)=>{if(!ok)throw Error(code);};
 const gcd=(a,b)=>{a=a<0n?-a:a;while(b){[a,b]=[b,a%b];}return a||1n;};
 const frac=(n,d=1n)=>{need(d>0n,'invalid_denominator');const g=gcd(n,d);return {n:n/g,d:d/g};};
 const sum=(a,b)=>frac(a.n*b.d+b.n*a.d,a.d*b.d),scale=(a,n,d=1n)=>frac(a.n*n,a.d*d);
 const compare=(a,b)=>a.n*b.d<b.n*a.d?-1:a.n*b.d>b.n*a.d?1:0;
 function decimal(a,places=6){const factor=10n**BigInt(places),negative=a.n<0n,n=negative?-a.n:a.n,q=(n*factor*2n+a.d)/(2n*a.d),s=q.toString().padStart(places+1,'0');return (negative&&q?'−':'')+(places?s.slice(0,-places)+'.'+s.slice(-places):s);}
 const ascii=a=>decimal(a).replace('−','-');
 const number=a=>Number(a.n)/Number(a.d);
 // Each factory owns a detached, deeply frozen version contract; runtime options cannot override it.
 function createModel(input){
  const config=JSON.parse(JSON.stringify(input));
  need(config&&typeof config.model_version==='string'&&config.model_version.length>0,'model_version_invalid');
  const registered=registry.VERSIONS[config.model_version];
  need(!registered||JSON.stringify(config)===JSON.stringify(registered),'model_version_conflict');
  need(config.algorithm==='smoothed_yoy_midrank_v1','unsupported_algorithm');
  const entries=config.indicators,method=config.methodology;
  need(Array.isArray(entries)&&entries.length>=2,'registry_entries_invalid');
  need(new Set(entries.map(e=>e.id)).size===entries.length,'registry_duplicate_id');
  const keys=['source','unit','publisher','verification','method','definition'];
  for(const e of entries){
   need(typeof e.id==='string'&&e.id.length>0&&typeof e.revision==='string'&&e.revision.length>0&&registry.DOMAINS.includes(e.domain)&&typeof e.label==='string'&&e.label.length>0&&typeof e.weight_label==='string'&&e.weight_label.length>0,'registry_entry_invalid');
   need(e.contract&&keys.every(k=>typeof e.contract[k]==='string'&&e.contract[k].length>0),'registry_contract_invalid');
   const v=e.validation,u=v?.url;
   need(v&&u&&(typeof u.exact==='string'||(typeof u.hostname==='string'&&typeof u.pathname==='string')),'registry_validation_invalid');
   need(Object.keys(v).every(k=>['url','rights','file_sha256','period_from','period_through','scope_error'].includes(k))&&Object.keys(u).every(k=>['exact','hostname','pathname'].includes(k)),'registry_validation_invalid');
   need((!v.period_from&&!v.period_through)||(month(v.period_from)&&month(v.period_through)&&v.period_from<=v.period_through),'registry_validation_invalid');
   need(v.scope_error===undefined||['approved_scope_exceeded','tourgo_scope_exceeded'].includes(v.scope_error),'registry_validation_invalid');
   need((v.rights===undefined||typeof v.rights==='string')&&(v.file_sha256===undefined||typeof v.file_sha256==='boolean'),'registry_validation_invalid');
   need(Number.isSafeInteger(e.weight?.numerator)&&e.weight.numerator>0&&Number.isSafeInteger(e.weight?.denominator)&&e.weight.denominator>0,'registry_weight_invalid');
  }
  const weights=entries.map(e=>frac(BigInt(e.weight.numerator),BigInt(e.weight.denominator)));
  need(compare(weights.reduce(sum,frac(0n)),frac(1n))===0,'registry_weight_sum_invalid');
  // This algorithm revision fixes transforms/window semantics; new formulas require a new algorithm.
  need(method&&method.yoy==='100*(x[t]/x[t-12]-1)'&&method.smoothing_months===3&&method.reference_months===24&&method.percentile==='100*(strictly_lower+0.5*equal)/24; reference excludes target month'&&method.mode==='retrospective_current_vintage'&&method.seasonal_adjustment===false,'registry_methodology_invalid');
  need(Array.isArray(method.weights)&&method.weights.length===weights.length&&method.weights.every((w,n)=>w===number(weights[n])),'registry_weight_mismatch');
  need(Array.isArray(method.weather_cutoffs)&&method.weather_cutoffs.length===3&&method.weather_cutoffs.every((v,n,a)=>Number.isSafeInteger(v)&&v>0&&v<100&&(!n||v>a[n-1]))&&Number.isSafeInteger(method.max_lag_months)&&method.max_lag_months>=1,'registry_methodology_invalid');
  registry.freeze(config);
  const VERSION=config.model_version,IDS=Object.freeze(entries.map(e=>e.id)),CONTRACT=Object.freeze(entries.map(e=>e.contract)),METHOD=config.methodology;
 function official(url,rule){try{const u=new URL(url);return !u.username&&!u.password&&u.protocol==='https:'&&(rule.exact?url===rule.exact:u.hostname===rule.hostname&&u.pathname===rule.pathname);}catch{return false;}}
 function rows(i,entry,target,current){
  const c=entry.contract,validation=entry.validation;
  need(i&&i.enabled===true&&i.connected===true,'series_not_connected');
  need(i.source_id===c.source&&i.unit===c.unit&&i.publisher===c.publisher&&i.definition===c.definition&&i.frequency==='M'&&!i.country&&official(i.source_url,validation.url),'indicator_contract_mismatch');
  need(Array.isArray(i.observations),'observations_invalid');
  const start=add(target,-38),map=new Map();let first=null;
  for(const o of i.observations){
   need(o&&month(o.period),'observation_period_invalid');if(o.period>target)continue;
   if(first===null||o.period<first)first=o.period;
   if(o.period<start)continue;
   need(!map.has(o.period),'duplicate_period');
   need(Number.isSafeInteger(o.value)&&o.value>=0&&o.unit===c.unit&&o.frequency==='M'&&o.publisher===c.publisher&&o.verification_status===c.verification&&o.collection_method===c.method&&official(o.source_url,validation.url)&&['not_stated','provisional','final'].includes(o.finality)&&(!('definition' in o)||o.definition===c.definition),'observation_contract_mismatch');
   if(validation.period_from)need(o.period>=validation.period_from&&o.period<=validation.period_through,validation.scope_error||'approved_scope_exceeded');
   if(validation.rights)need(o.rights===validation.rights,'official_file_evidence_missing');
   if(validation.file_sha256)need(/^[a-f0-9]{64}$/.test(o.file_sha256||''),'official_file_evidence_missing');
   map.set(o.period,o);
  }
  need(first!==null&&start>=first,'insufficient_reference_history');
  for(let n=-38;n<=0;n++)need(map.has(add(target,n)),'missing_observation');
  if(current){const saved=map.get(target),latest=i.latest;
   need(latest&&['period','value','unit','frequency','publisher','source_url','verification_status','collection_method'].every(k=>latest[k]===saved[k]),'latest_observation_mismatch');
   const base=map.get(add(target,-12)).value;
   need(base>0,'zero_yoy_denominator');
   const pct=frac(100n*(BigInt(saved.value)-BigInt(base)),BigInt(base));
   need(latest.comparisons?.reference_period===target&&latest.comparisons?.yoy_base_period===add(target,-12)&&typeof latest.comparisons?.yoy_pct==='number'&&latest.comparisons.yoy_pct===Number(decimal(pct,2).replace('−','-')),'supplied_yoy_mismatch');
  }
  return map;
 }
 function axis(i,entry,weight,target,current){
  const c=entry.contract,map=rows(i,entry,target,current),growth=new Map();
  for(let n=-26;n<=0;n++){const p=add(target,n),a=map.get(p).value,b=map.get(add(p,-12)).value;need(b>0,'zero_yoy_denominator');growth.set(p,frac(100n*(BigInt(a)-BigInt(b)),BigInt(b)));}
  const smooth=p=>scale(sum(sum(growth.get(p),growth.get(add(p,-1))),growth.get(add(p,-2))),1n,3n);
  const value=smooth(target),reference=Array.from({length:24},(_,n)=>smooth(add(target,n-24))),sorted=[...reference].sort(compare);
  need(compare(sorted[0],sorted[23])!==0,'degenerate_reference_distribution');
  const lower=reference.filter(v=>compare(v,value)<0).length,ties=reference.filter(v=>compare(v,value)===0).length;
  const position=frac(BigInt(100*(2*lower+ties)),48n),warnings=[];
  if(add(target,-38)<='2022-12')warnings.push('pandemic_baseline_in_reference');
  if(ties)warnings.push('ties_can_be_revision_sensitive');
  if(compare(value,sorted[0])<0||compare(value,sorted[23])>0)warnings.push('outside_reference_range');
  if([...map.values()].some(o=>o.revision_status==='revised'))warnings.push('revised_input_vintage');
  return {rank:position,data:{indicator_id:i.id,value:map.get(target).value,unit:c.unit,yoy_pct:ascii(growth.get(target)),smoothed_yoy_pct:ascii(value),percentile:ascii(position),contribution:ascii(scale(position,weight.n,weight.d)),
   source_url:map.get(target).source_url,publisher:c.publisher,definition:c.definition,finality:map.get(target).finality,
   last_collected_at:map.get(target).last_collected_at||null,original_publication_at:map.get(target).original_publication_at||null,
   reference_from:add(target,-24),reference_through:add(target,-1),input_from:add(target,-38),input_through:target,reference_count:24,tie_count:ties,warnings}};
 }
 function withheld(period,reason){return {model_version:VERSION,reference_period:period||null,source_indicator_ids:[...IDS],methodology:METHOD,status:'withheld',reason,score:null,score_display:null,weather:null,axes:[],warnings:['experimental_partial_signal','retrospective_current_vintage','not_an_official_index_or_forecast','nominal_usd_not_real_consumption']};}
 function evaluate(db,options={}){
  let target=options.reference_period||null;
  try{
   need(db?.schema_version===1&&db.mode==='verified_official_statistics'&&Array.isArray(db.indicators),'verified_database_required');
   const series=IDS.map(id=>{const a=db.indicators.filter(i=>i.id===id);need(a.length===1,'indicator_identity_invalid');return a[0];});
   const current=!target;
   if(current){need(series.every(i=>month(i.latest?.period)),'latest_period_unavailable');need(series.every(i=>i.latest.period===series[0].latest.period),'latest_period_mismatch');target=series[0].latest.period;}
   need(month(target),'target_period_invalid');
   const asOf=options.as_of_period||db.generated_at?.slice(0,7);need(month(asOf),'analysis_month_required');
   need(target<asOf,'future_or_incomplete_month');need(distance(asOf,target)<=METHOD.max_lag_months,'stale_reference_period');
   const axes=series.map((i,n)=>axis(i,entries[n],weights[n],target,current)),score=axes.reduce((total,a,n)=>sum(total,scale(a.rank,weights[n].n,weights[n].d)),frac(0n));
   const cutoffs=METHOD.weather_cutoffs.map(v=>frac(BigInt(v))),tone=compare(score,cutoffs[0])<0?'rain':compare(score,cutoffs[1])<0?'cloudy':compare(score,cutoffs[2])<0?'partly':'sunny';
   return {...withheld(target,null),status:'observed',score:number(score),score_display:decimal(score,2),score_exact:ascii(score),weather:tone,axes:axes.map(a=>a.data)};
  }catch(e){return withheld(target,SAFE.has(e.message)?e.message:'input_contract_invalid');}
 }
 const SAFE=new Set(['approved_scope_exceeded','invalid_denominator','series_not_connected','indicator_contract_mismatch','observations_invalid','observation_period_invalid','duplicate_period','observation_contract_mismatch','tourgo_scope_exceeded','official_file_evidence_missing','insufficient_reference_history','missing_observation','latest_observation_mismatch','zero_yoy_denominator','supplied_yoy_mismatch','degenerate_reference_distribution','verified_database_required','indicator_identity_invalid','latest_period_unavailable','latest_period_mismatch','target_period_invalid','analysis_month_required','future_or_incomplete_month','stale_reference_period']);
 function walkForward(db,end){
  const periods=[...new Set((db?.indicators?.find(i=>i.id===IDS[0])?.observations||[]).map(o=>o.period).filter(p=>month(p)&&(!end||p<=end)))].sort(),points=[];
  let failures=0;
  for(const period of periods){
   const options={reference_period:period,as_of_period:add(period,1)},result=evaluate(db,options);
   const prefix={...db,indicators:db.indicators.filter(i=>IDS.includes(i.id)).map(i=>{const observations=i.observations.filter(o=>month(o.period)&&o.period<=period);return {...i,observations,latest:observations.at(-1)||null};})};
   const match=JSON.stringify(result)===JSON.stringify(evaluate(prefix,options));
   if(!match||(result.status==='observed'&&(!Number.isFinite(result.score)||result.score<0||result.score>100)))failures++;
   points.push({reference_period:period,status:result.status,reason:result.reason,score:result.score,weather:result.weather,future_prefix_match:match,axes:result.axes});
  }
  return {mode:'retrospective_current_vintage',historical_as_of_verified:false,prediction_accuracy_measured:false,evaluated_months:points.length,scored_months:points.filter(p=>p.status==='observed').length,withheld_months:points.filter(p=>p.status!=='observed').length,invariant_failures:failures,points};
 }
 function run(db,options={}){
  const result=evaluate(db,options);let backtest;
  try{backtest=walkForward(db,result.reference_period||undefined);}catch{return {...withheld(result.reference_period,'backtest_failed'),backtest:{invariant_failures:1}};}
  if(backtest.invariant_failures)return {...withheld(result.reference_period,'backtest_failed'),backtest};
  return {...result,backtest};
 }
 return Object.freeze({VERSION,IDS,METHOD,CONTRACT,CONFIG:config,evaluate,walkForward,run,addMonth:add});
 }
 const model=createModel(registry.VERSIONS['model-signal-v1.0.0']);
 return Object.freeze({...model,createModel,INDICATOR_REGISTRY:registry.INDICATORS,MODEL_VERSIONS:registry.VERSIONS});
});
