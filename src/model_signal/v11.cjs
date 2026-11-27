/* Private candidate only. No fetch, writes, DOM, approval or operating registration. */
'use strict';
const crypto=require('node:crypto'),v1=require('../../site/market-signal-model.js');
const VERSION='model-signal-v1.1.0-draft';
const CONFIG=Object.freeze({model_version:VERSION,base_version:v1.VERSION,methodology:v1.METHOD,
 alignment:'earliest_latest_month_then_validate_39_consecutive_months',max_lag_months:3});
const month=p=>typeof p==='string'&&/^(19|20)\d\d-(0[1-9]|1[0-2])$/.test(p);
const need=(condition,code)=>{if(!condition)throw Object.assign(Error(code),{safe:code});};
const hash=raw=>crypto.createHash('sha256').update(raw).digest('hex');
function evaluateSnapshot(raw,options={}){
 let target=null,latest={},sha=null;
 const withheld=reason=>({model_version:VERSION,base_version:v1.VERSION,status:'withheld',reason,
  analysis_period:options.as_of_period||null,reference_period:target,score:null,score_display:null,weather:null,axes:[],latest_observation_periods:latest,
  input_sha256:sha,methodology:CONFIG,source_indicator_ids:[...v1.IDS],publication_approved:false,
  mode:'retrospective_current_vintage',historical_as_of_verified:false});
 try{
  need(Buffer.isBuffer(raw)&&raw.length<=32*1024*1024,'snapshot_bytes_required');sha=hash(raw);
  need(/^[a-f0-9]{64}$/.test(options.expected_sha256||'')&&sha===options.expected_sha256,'snapshot_hash_mismatch');
  const db=JSON.parse(raw.toString('utf8'));
  need(db?.schema_version===1&&db.mode==='verified_official_statistics'&&Array.isArray(db.indicators),'verified_database_required');
  need(month(options.as_of_period),'analysis_month_required');
  if(options.reference_period)need(month(options.reference_period)&&options.reference_period<options.as_of_period,'future_or_incomplete_month');
  const cutoff=options.reference_period||v1.addMonth(options.as_of_period,-1),sets=[];
  for(const [n,id] of v1.IDS.entries()){
   const matches=db.indicators.filter(i=>i.id===id);need(matches.length===1,'indicator_identity_invalid');
   const i=matches[0],entry=v1.CONFIG.indicators[n],c=entry.contract;
   need(i.enabled===true&&i.connected===true,'series_not_connected');need(Array.isArray(i.observations),'observations_invalid');
   const seen=new Map();
   for(const o of i.observations){
    need(o&&month(o.period),'observation_period_invalid');if(o.period>cutoff)continue;
    need(!seen.has(o.period),'duplicate_period');
    if(entry.validation.period_from)need(o.period>=entry.validation.period_from&&o.period<=entry.validation.period_through,'tourgo_scope_exceeded');
    seen.set(o.period,o);
   }
   need(seen.size>0,'latest_period_unavailable');const p=[...seen.keys()].sort().at(-1);latest[id]=p;
   // Validate the true visible latest even when the common month is older. Never relabel it.
   const o=seen.get(p),l=i.latest;
   if(!options.reference_period&&(!month(l?.period)||l.period<=cutoff)){
    need(l&&l.period===p&&Object.keys(o).every(k=>JSON.stringify(l[k])===JSON.stringify(o[k])),'latest_observation_mismatch');
    const b=seen.get(v1.addMonth(p,-12));need(b&&Number.isSafeInteger(b.value)&&b.value>0,'zero_yoy_denominator');
    need(Number.isSafeInteger(o.value)&&o.value>=0,'observation_contract_mismatch');
    const num=10000n*(BigInt(o.value)-BigInt(b.value)),den=BigInt(b.value),sign=num<0n?-1n:1n;
    const rounded=Number(sign*((2n*(num<0n?-num:num)+den)/(2n*den)))/100;
    need(l.comparisons?.reference_period===p&&l.comparisons?.yoy_base_period===b.period&&l.comparisons?.yoy_pct===rounded,'supplied_yoy_mismatch');
   }
   need(o.unit===c.unit&&o.frequency==='M'&&o.publisher===c.publisher&&o.verification_status===c.verification&&o.collection_method===c.method&&(!('definition' in o)||o.definition===c.definition)&&Number.isSafeInteger(o.value)&&o.value>=0&&['not_stated','provisional','final'].includes(o.finality),'observation_contract_mismatch');
   let url;try{url=new URL(o.source_url);}catch{need(false,'official_file_evidence_missing');}
   const rule=entry.validation.url;
   need(url.protocol==='https:'&&!url.username&&!url.password&&(rule.exact?o.source_url===rule.exact:url.hostname===rule.hostname&&url.pathname===rule.pathname),'official_file_evidence_missing');
   if(entry.validation.file_sha256)need(/^[a-f0-9]{64}$/.test(o.file_sha256||''),'official_file_evidence_missing');
   if(entry.validation.rights)need(o.rights===entry.validation.rights,'official_file_evidence_missing');
   sets.push(seen);
  }
  // Pin the expected month before testing presence; an internal gap must never trigger fallback.
  target=options.reference_period||Object.values(latest).sort()[0];
  need(sets.every(s=>s.has(target)),'target_common_month_unavailable');
  for(const seen of sets)for(const o of seen.values())if(o.period>=v1.addMonth(target,-38)&&o.period<=target){
   if(o.revision_status!==undefined)need(['original','revised'].includes(o.revision_status),'revision_metadata_invalid');
   for(const key of ['release_published_at','original_publication_at','first_collected_at','last_collected_at'])
    if(o[key]!==null&&o[key]!==undefined)need(typeof o[key]==='string'&&/(Z|[+-]\d\d:\d\d)$/.test(o[key])&&Number.isFinite(Date.parse(o[key])),'publication_metadata_invalid');
   if(o.first_collected_at&&o.last_collected_at)need(Date.parse(o.first_collected_at)<=Date.parse(o.last_collected_at),'publication_metadata_invalid');
  }
  // Reuse the unchanged exact BigInt/Fraction engine, contracts, 39-month window and lag gate.
  const result=v1.evaluate(db,{reference_period:target,as_of_period:options.as_of_period});
  if(result.status!=='observed')return {...withheld(result.reason),warnings:result.warnings};
  return {...result,model_version:VERSION,base_version:v1.VERSION,input_sha256:sha,latest_observation_periods:latest,
   alignment_reason:Object.values(latest).every(p=>p===target)?'latest_months_aligned':'last_common_official_month',
   lag_months:(+options.as_of_period.slice(0,4)-+target.slice(0,4))*12+(+options.as_of_period.slice(5)-+target.slice(5)),
   analysis_period:options.as_of_period,input_generated_at:db.generated_at||null,publication_approved:false,mode:'retrospective_current_vintage',historical_as_of_verified:false,
   limitations:['partial_inbound_and_nominal_receipts_only','original_publication_dates_not_fully_verified','not_an_official_index_or_forecast'],
   source_roles:{kto_inbound:'official_public_xlsx_automated_collection',kto_tourism_receipts:'operator_supplied_manual_TOURGO_file'},methodology:CONFIG};
 }catch(e){return withheld(e.safe||'snapshot_or_contract_invalid');}
}
module.exports=Object.freeze({VERSION,CONFIG,evaluateSnapshot,hash});
