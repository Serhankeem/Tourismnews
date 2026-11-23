'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const model=require('../site/market-signal-model.js');
const clone=v=>JSON.parse(JSON.stringify(v));
const options={reference_period:'2026-09',as_of_period:'2026-11'};
function fixture(config=model.CONFIG){
 return {schema_version:1,mode:'verified_official_statistics',generated_at:'2026-11-23T00:00:00Z',indicators:config.indicators.map(e=>{
  const c=e.contract,v=e.validation,url=v.url.exact||`https://${v.url.hostname}${v.url.pathname}`;
  const observations=Array.from({length:69},(_,n)=>({period:model.addMonth('2021-01',n),value:(1+Math.floor(n/12))*1000,unit:c.unit,frequency:'M',publisher:c.publisher,source_url:url,verification_status:c.verification,collection_method:c.method,finality:'not_stated',...(v.rights?{rights:v.rights}:{}),...(v.file_sha256?{file_sha256:'a'.repeat(64)}:{})}));
  return {id:e.id,source_id:c.source,unit:c.unit,publisher:c.publisher,definition:c.definition,source_url:url,frequency:'M',enabled:true,connected:true,observations,latest:{...observations.at(-1),comparisons:{reference_period:'2026-09',yoy_base_period:'2025-09',yoy_pct:20}}};
 })};
}
function threeConfig(){
 const config=clone(model.CONFIG);config.model_version='synthetic-three-series-test-only';
 const extra=clone(config.indicators[0]);Object.assign(extra,{id:'synthetic_activity_test_only',domain:'industry',label:'SYNTHETIC ONLY',weight_label:'SYNTHETIC ONLY'});
 Object.assign(extra.contract,{source:'synthetic_fixture',unit:'synthetic_count',publisher:'TEST ONLY',definition:'Synthetic monthly activity; never operational'});
 extra.validation={url:{exact:'https://synthetic.example.invalid/monthly'},rights:'SYNTHETIC_TEST_ONLY',file_sha256:true};
 config.indicators.push(extra);config.indicators.forEach((e,n)=>e.weight=[{numerator:1,denominator:2},{numerator:1,denominator:3},{numerator:1,denominator:6}][n]);
 config.methodology.weights=[.5,1/3,1/6];config.methodology.scope='synthetic_test_only';return config;
}
test('production registry declares six domains but activates only the two pinned v1 contracts',()=>{
 assert.equal(model.INDICATOR_REGISTRY.length,2);assert.deepEqual(model.IDS,['kto_inbound','kto_tourism_receipts']);
 assert.deepEqual(model.CONFIG.indicators.map(e=>e.domain),['demand','consumption']);
 assert.deepEqual(require('../site/market-signal-registry.js').DOMAINS,['demand','consumption','supply','industry','macro','sentiment']);
 for(const e of model.CONFIG.indicators){assert.ok(e.contract.definition);assert.ok(e.validation.url);assert.deepEqual(e.weight,{numerator:1,denominator:2});}
});
test('three declared series use exact nonuniform weights and generic contracts, without a core algorithm edit',()=>{
 const config=threeConfig(),m=model.createModel(config),db=fixture(config),before=JSON.stringify(db);
 db.indicators[0].observations.at(-1).value=6001;db.indicators[1].observations.at(-1).value=7000;db.indicators[2].observations.at(-1).value=Number.MAX_SAFE_INTEGER;
 const input=JSON.stringify(db),r=m.run(db,options);
 assert.equal(r.status,'observed');assert.deepEqual(r.axes.map(a=>a.percentile),['25.000000','75.000000','100.000000']);
 assert.deepEqual(r.axes.map(a=>a.contribution),['12.500000','25.000000','16.666667']);
 assert.equal(r.score,325/6);assert.equal(r.score_exact,'54.166667');assert.equal(r.weather,'partly');
 assert.equal(r.backtest.invariant_failures,0);assert.equal(r.backtest.scored_months,31);assert.equal(JSON.stringify(db),input);assert.notEqual(input,before);
 assert.equal(model.INDICATOR_REGISTRY.length,2);assert.equal(model.IDS.includes('synthetic_activity_test_only'),false);
});
test('missing, disconnected, wrong metadata, missing rights and duplicate third-series data withhold all three',()=>{
 for(const change of [d=>d.indicators.pop(),d=>d.indicators[2].connected=false,d=>d.indicators[2].unit='wrong',d=>d.indicators[2].observations.at(-1).rights='wrong',d=>d.indicators[2].observations.push({...d.indicators[2].observations.at(-1)})]){
  const config=threeConfig(),m=model.createModel(config),db=fixture(config);change(db);const r=m.evaluate(db,options);assert.equal(r.status,'withheld');assert.equal(r.score,null);
 }
});
test('third latest-month mismatch is checked, not only the original two',()=>{
 const config=threeConfig(),m=model.createModel(config),db=fixture(config);db.indicators[2].latest.period='2026-08';assert.equal(m.evaluate(db,{as_of_period:'2026-11'}).reason,'latest_period_mismatch');
});
test('same generic algorithm supports four series with valid rational weights',()=>{
 const config=threeConfig(),extra=clone(config.indicators[2]);extra.id='synthetic_fourth_test_only';config.indicators.push(extra);
 config.model_version='synthetic-four-series-test-only';config.indicators.forEach(e=>e.weight={numerator:1,denominator:4});config.methodology.weights=[.25,.25,.25,.25];
 const r=model.createModel(config).run(fixture(config),options);assert.equal(r.status,'observed');assert.equal(r.axes.length,4);assert.equal(r.score,12.5);assert.equal(r.backtest.invariant_failures,0);
});
test('registration alone does not activate or change any existing edition',()=>{
 const db=fixture(),before=model.run(db,options),extended=clone(model.INDICATOR_REGISTRY);extended.push(threeConfig().indicators[2]);
 db.indicators.push(fixture(threeConfig()).indicators[2]);assert.deepEqual(model.run(db,options),before);
 const registry=require('../site/market-signal-registry.js');
 assert.deepEqual(registry.defineVersion(extended,registry.MANIFESTS[model.VERSION]),model.CONFIG);
 assert.equal(model.CONFIG.indicators.length,2);assert.equal(model.MODEL_VERSIONS[model.VERSION].indicators.length,2);assert.equal(extended.length,3);
});
test('version snapshots, contracts, nested validation and methodology are deeply frozen and detached',()=>{
 const config=threeConfig(),m=model.createModel(config),db=fixture(config),before=m.run(db,options);
 config.indicators[0].weight.numerator=999;config.indicators[0].contract.unit='mutated';config.methodology.weather_cutoffs[0]=1;
 assert.deepEqual(m.run(db,options),before);
 for(const mutate of [()=>m.CONFIG.indicators.push({}),()=>m.CONFIG.indicators[0].weight.numerator=99,()=>m.CONFIG.indicators[0].validation.url.hostname='evil.invalid',()=>model.INDICATOR_REGISTRY[0].contract.unit='changed',()=>model.MODEL_VERSIONS[model.VERSION].methodology.weights[0]=1])assert.throws(mutate,TypeError);
});
test('same edition name cannot silently acquire different weights, definitions, active set or weather cutoffs',()=>{
 for(const change of [c=>c.indicators[0].weight.numerator=2,c=>c.indicators[0].contract.definition+='changed',c=>c.indicators.pop(),c=>c.methodology.weather_cutoffs[0]=20]){const c=clone(model.CONFIG);change(c);assert.throws(()=>model.createModel(c),/model_version_conflict/);}
 assert.deepEqual(model.createModel(clone(model.CONFIG)).evaluate(fixture(),options),model.evaluate(fixture(),options));
});
test('invalid registry IDs, domains, contracts, rules, periods and weights are rejected before calculation',()=>{
 const changes=[c=>c.indicators[2].id=c.indicators[0].id,c=>c.indicators[2].domain='unknown',c=>delete c.indicators[2].contract.definition,c=>delete c.indicators[2].validation.url,c=>c.indicators[2].validation.unimplemented_rule=true,c=>c.indicators[2].validation.period_from='2027-01',c=>c.indicators[2].weight.numerator=0,c=>c.indicators[2].weight.denominator=0,c=>c.indicators[2].weight.numerator=1.5,c=>c.indicators[2].weight.numerator=2,c=>c.methodology.weights[2]=.5];
 for(const change of changes){const c=threeConfig();change(c);assert.throws(()=>model.createModel(c),/registry_/);}
});
test('unsupported transforms, windows or algorithm revisions cannot be silently ignored',()=>{
 for(const change of [c=>c.algorithm='unimplemented',c=>c.methodology.smoothing_months=6,c=>c.methodology.reference_months=12,c=>c.methodology.yoy='momentum',c=>c.methodology.weather_cutoffs=[75,50,25]]){const c=threeConfig();change(c);assert.throws(()=>model.createModel(c),/unsupported_algorithm|registry_methodology_invalid/);}
});
test('extra future values in any registered axis cannot leak into a three-series past result',()=>{
 const config=threeConfig(),m=model.createModel(config),db=fixture(config),o={reference_period:'2025-06',as_of_period:'2025-07'},before=m.run(db,o);
 for(const i of db.indicators)for(const v of i.observations)if(v.period>'2025-06')v.value=Number.MAX_SAFE_INTEGER;
 assert.deepEqual(m.run(db,o),before);
});
test('registry order does not replace ID mapping or change an existing version result',()=>{
 const db=fixture(),before=model.run(db,options);db.indicators.reverse();assert.deepEqual(model.run(db,options),before);
 const config=threeConfig(),m=model.createModel(config),three=fixture(config),a=m.evaluate(three,options);three.indicators.reverse();assert.deepEqual(m.evaluate(three,options),a);
});

test('unavailable or duplicate contract revisions cannot resolve a model edition',()=>{
 const r=require('../site/market-signal-registry.js'),manifest=r.MANIFESTS[model.VERSION];
 assert.throws(()=>r.defineVersion([],manifest),/registry_revision_identity_invalid/);
 assert.throws(()=>r.defineVersion([...r.INDICATORS,r.INDICATORS[0]],manifest),/registry_revision_identity_invalid/);
 const newer=clone(r.INDICATORS[0]);newer.revision='2';newer.contract.definition+=' revision two';
 assert.deepEqual(r.defineVersion([...r.INDICATORS,newer],manifest),model.CONFIG);
});
test('the full v1 edition fingerprint is pinned independently of mutable future editions',()=>{
 const canonical=v=>Array.isArray(v)?'['+v.map(canonical).join(',')+']':v&&typeof v==='object'?'{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}':JSON.stringify(v);
 const digest=require('node:crypto').createHash('sha256').update(canonical(model.CONFIG)).digest('hex');
 assert.equal(digest,'47602b7f2f459ca14e9a35e6053ecd5b129a0a51047c940d3c284c544dfebc84');
});
