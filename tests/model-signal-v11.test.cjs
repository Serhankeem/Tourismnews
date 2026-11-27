'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),v1=require('../site/market-signal-model.js'),m=require('../src/model_signal/v11.cjs');
const options={as_of_period:'2026-11'};
function fixture(){
 const indicators=v1.IDS.map((id,j)=>{const c=v1.CONTRACT[j],source_url=j?'https://know.tour.go.kr/stat/koreaTourIncomeDis19Re.do':'https://datalab.visitkorea.or.kr/site/portal/ex/bbs/View.do?cbIdx=1603';
 const observations=Array.from({length:69},(_,n)=>({period:v1.addMonth('2021-01',n),value:(1+Math.floor(n/12))*1000*(j?1000000:1),unit:c.unit,frequency:'M',publisher:c.publisher,source_url,verification_status:c.verification,collection_method:c.method,finality:'not_stated',revision_status:'original',...(j?{}:{rights:'KOGL-0',file_sha256:'a'.repeat(64)})}));
 return {id,source_id:c.source,unit:c.unit,publisher:c.publisher,definition:c.definition,source_url,frequency:'M',enabled:true,connected:true,observations};});
 const db={schema_version:1,mode:'verified_official_statistics',generated_at:'2026-11-20T00:00:00Z',indicators};sync(db);return db;
}
function sync(db){for(const i of db.indicators){const o=[...i.observations].sort((a,b)=>a.period.localeCompare(b.period)).at(-1),b=i.observations.find(x=>x.period===v1.addMonth(o.period,-12));i.latest={...o,comparisons:{reference_period:o.period,yoy_base_period:v1.addMonth(o.period,-12),yoy_pct:b?.value?Number((100*(o.value/b.value-1)).toFixed(2)):null}};}}
function evaluate(db,opts={}){const raw=Buffer.from(JSON.stringify(db));return m.evaluateSnapshot(raw,{expected_sha256:m.hash(raw),...options,...opts});}
function trim(db,j,month){db.indicators[j].observations=db.indicators[j].observations.filter(o=>o.period<=month);sync(db);}
test('aligned common month preserves exact v1 axes, score and bands without mutating v1',()=>{const db=fixture(),before=JSON.stringify(db),a=v1.evaluate(db,options),b=evaluate(db);assert.equal(b.score,a.score);assert.deepEqual(b.axes,a.axes);assert.equal(b.model_version,'model-signal-v1.1.0-draft');assert.equal(v1.VERSION,'model-signal-v1.0.0');assert.equal(JSON.stringify(db),before);assert.equal(b.publication_approved,false);});
test('KTO one month ahead selects the earlier actual common month, not mixed inputs',()=>{const db=fixture();trim(db,1,'2026-08');const b=evaluate(db);assert.equal(b.status,'observed');assert.equal(b.reference_period,'2026-08');assert.deepEqual(b.latest_observation_periods,{kto_inbound:'2026-09',kto_tourism_receipts:'2026-08'});assert.equal(b.alignment_reason,'last_common_official_month');assert.equal(b.score,v1.evaluate(db,{...options,reference_period:'2026-08'}).score);assert.equal(v1.evaluate(db,options).reason,'latest_period_mismatch');});
test('TOURGO one month ahead within existing approved scope also aligns',()=>{const db=fixture();trim(db,0,'2026-08');assert.equal(evaluate(db).reference_period,'2026-08');assert.equal(evaluate(db).status,'observed');});
test('a gap in selected 39-month window withholds; never search for an older successful score',()=>{const db=fixture();db.indicators[0].observations=db.indicators[0].observations.filter(o=>o.period!=='2024-03');assert.equal(evaluate(db).reason,'missing_observation');});
test('three-month lag is inclusive and four months withholds',()=>{const db=fixture();assert.equal(evaluate(db,{as_of_period:'2026-12'}).status,'observed');assert.equal(evaluate(db,{as_of_period:'2027-01'}).reason,'stale_reference_period');});
test('too short history, duplicates and zero denominators do not fill or reweight',()=>{for(const [change,reason] of [[d=>d.indicators[0].observations=d.indicators[0].observations.slice(-38),'insufficient_reference_history'],[d=>d.indicators[0].observations.push({...d.indicators[0].observations[40]}),'duplicate_period'],[d=>d.indicators[0].observations[55].value=0,'zero_yoy_denominator']]){const db=fixture();change(db);const r=evaluate(db);assert.equal(r.reason,reason);assert.equal(r.score,null);}});
test('an out-of-approved-scope receipt is blocked even if another series is behind',()=>{const db=fixture();db.indicators[1].observations.push({...db.indicators[1].observations.at(-1),period:'2026-10'});sync(db);assert.equal(evaluate(db).reason,'tourgo_scope_exceeded');});
test('definition, unit, rights, file evidence, disconnected or absent series cannot pass alignment',()=>{for(const change of [d=>d.indicators[0].definition+='wrong',d=>d.indicators[0].unit='천 명',d=>d.indicators[0].observations.at(-1).rights='unknown',d=>d.indicators[0].observations.at(-1).file_sha256='',d=>d.indicators[1].connected=false,d=>d.indicators.pop()]){const db=fixture();change(db);sync(db);assert.equal(evaluate(db).status,'withheld');}});
test('older common month does not mask invalid evidence or duplicate latest values in advanced series',()=>{for(const change of [d=>d.indicators[0].latest.value++,d=>d.indicators[0].latest.comparisons.yoy_pct++,d=>{d.indicators[0].observations.at(-1).rights='unknown';sync(d);}]){const db=fixture();trim(db,1,'2026-08');change(db);assert.equal(evaluate(db).status,'withheld');}});
test('input bytes require an explicit matching SHA; wrong, missing and modified bytes fail',()=>{const raw=Buffer.from(JSON.stringify(fixture()));for(const expected_sha256 of [undefined,'a'.repeat(64)])assert.equal(m.evaluateSnapshot(raw,{...options,expected_sha256}).reason,'snapshot_hash_mismatch');assert.equal(m.evaluateSnapshot(Buffer.concat([raw,Buffer.from(' ')]),{...options,expected_sha256:m.hash(raw)}).reason,'snapshot_hash_mismatch');});
test('coherent revised snapshot is recalculated deterministically and original preserved',()=>{const db=fixture(),before=JSON.stringify(db),revised=structuredClone(db);revised.indicators[0].observations.at(-1).value++;revised.indicators[0].observations.at(-1).revision_status='revised';sync(revised);assert.notEqual(evaluate(revised).input_sha256,evaluate(db).input_sha256);assert.deepEqual(evaluate(revised),evaluate(revised));assert.ok(evaluate(revised).axes[0].warnings.includes('revised_input_vintage'));assert.equal(JSON.stringify(db),before);});
test('walk-forward prefix versus future values produces identical numeric results; explicit target cannot see future',()=>{const db=fixture(),opts={reference_period:'2025-06',as_of_period:'2025-07'},a=evaluate(db,opts);for(const i of db.indicators)for(const o of i.observations)if(o.period>'2025-06')o.value=999999999;sync(db);const b=evaluate(db,opts);for(const k of ['score','weather','axes','reference_period','latest_observation_periods'])assert.deepEqual(a[k],b[k]);assert.equal(evaluate(db,{reference_period:'2026-11'}).reason,'future_or_incomplete_month');});
test('every walk-forward month agrees with a truncated prefix; hash differs as expected',()=>{const db=fixture();for(let n=38;n<69;n++){const p=v1.addMonth('2021-01',n),opts={reference_period:p,as_of_period:v1.addMonth(p,1)},prefix=structuredClone(db);for(const i of prefix.indicators)i.observations=i.observations.filter(o=>o.period<=p);sync(prefix);const a=evaluate(db,opts),b=evaluate(prefix,opts);assert.equal(a.status,b.status);assert.equal(a.score,b.score);assert.deepEqual(a.axes,b.axes);}});

test('unknown revision and malformed collection/publication evidence do not silently pass',()=>{for(const change of [d=>d.indicators[0].observations[50].revision_status='unverified',d=>d.indicators[0].observations[50].original_publication_at='not-a-date',d=>{const o=d.indicators[0].observations[50];o.first_collected_at='2026-11-20T00:00:00Z';o.last_collected_at='2026-11-19T00:00:00Z';}]){const db=fixture();change(db);assert.equal(evaluate(db).status,'withheld');}});

test('KTO October with September missing must withhold September, never fall back to August',()=>{
 const db=fixture(),i=db.indicators[0];
 i.observations.push({...i.observations.at(-1),period:'2026-10'});
 i.observations=i.observations.filter(o=>o.period!=='2026-09');sync(db);
 const result=evaluate(db);
 assert.equal(result.reference_period,'2026-09');
 assert.equal(result.status,'withheld');assert.equal(result.reason,'target_common_month_unavailable');
 assert.equal(result.score,null);assert.equal(result.weather,null);
 assert.deepEqual(result.latest_observation_periods,{kto_inbound:'2026-10',kto_tourism_receipts:'2026-09'});
});
test('an internal gap in an advanced TOURGO series cannot move the expected common month backwards',()=>{
 const db=fixture();trim(db,0,'2026-08');
 db.indicators[1].observations=db.indicators[1].observations.filter(o=>o.period!=='2026-08');sync(db);
 const result=evaluate(db);
 assert.equal(result.reference_period,'2026-08');assert.equal(result.status,'withheld');
 assert.equal(result.reason,'target_common_month_unavailable');assert.equal(result.score,null);
});
