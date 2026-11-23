/* Declarative contracts and immutable edition snapshots. No data or network access. */
(function(root,factory){if(typeof module==='object'&&module.exports)module.exports=factory();else root.MarketSignalRegistry=factory();})(globalThis,()=>{
 'use strict';
 function freeze(value){if(value&&typeof value==='object'){Object.values(value).forEach(freeze);Object.freeze(value);}return value;}
 const DOMAINS=['demand','consumption','supply','industry','macro','sentiment'];
 const contracts=[
  {source:'kto_monthly_statistics',unit:'명',publisher:'한국관광공사',verification:'official_file_validated',method:'official_public_xlsx',
   definition:'전체 외국인 입국자 중 관광객으로 볼 수 없는 일부 체류자격을 제외하고 재외국민 입국자를 포함한 한국관광통계 공표치. 승무원 포함. 순수 관광목적 입국자나 Foreign Visitors 행만의 합계와 다름.'},
  {source:'tourgo_tourism_balance',unit:'US$',publisher:'한국문화관광연구원 관광지식정보시스템(TOURGO)',verification:'official_tourgo_file_validated',method:'operator_supplied_official_excel_export',
   definition:'TOURGO 관광수입(일반여행수입); 유학연수를 포함한 전체 여행수지와 구분. 원본 천 US$, Macro 원장 US$.'}
 ];
 const indicators=[
  {id:'kto_inbound',revision:'1',domain:'demand',label:'방한 외래관광객 수',weight_label:'방한 수요',contract:contracts[0],
   validation:{url:{hostname:'datalab.visitkorea.or.kr',pathname:'/site/portal/ex/bbs/View.do'},rights:'KOGL-0',file_sha256:true}},
  {id:'kto_tourism_receipts',revision:'1',domain:'consumption',label:'일반여행수입 · 명목 US$',weight_label:'일반여행수입',contract:contracts[1],
   validation:{url:{exact:'https://know.tour.go.kr/stat/koreaTourIncomeDis19Re.do'},period_from:'2021-01',period_through:'2026-09',scope_error:'tourgo_scope_exceeded'}}
 ];
 function defineVersion(entries,manifest){
  const snapshot=JSON.parse(JSON.stringify(manifest));
  const active=snapshot.active_indicators;delete snapshot.active_indicators;
  snapshot.indicators=active.map(binding=>{
   const matches=entries.filter(e=>e.id===binding.id&&e.revision===binding.revision);
   if(matches.length!==1)throw Error('registry_revision_identity_invalid');
   return {...JSON.parse(JSON.stringify(matches[0])),weight:{...binding.weight}};
  });
  return freeze(snapshot);
 }
 const manifest={model_version:'model-signal-v1.0.0',algorithm:'smoothed_yoy_midrank_v1',
  // Registration NEVER implies activation. A new edition must explicitly select ID + revision + weight.
  active_indicators:[
   {id:'kto_inbound',revision:'1',weight:{numerator:1,denominator:2}},
   {id:'kto_tourism_receipts',revision:'1',weight:{numerator:1,denominator:2}}
  ],
  methodology:{yoy:'100*(x[t]/x[t-12]-1)',smoothing_months:3,reference_months:24,
   percentile:'100*(strictly_lower+0.5*equal)/24; reference excludes target month',weights:[0.5,0.5],
   weather_cutoffs:[25,50,75],max_lag_months:3,mode:'retrospective_current_vintage',seasonal_adjustment:false,
   scope:'inbound_demand_and_nominal_general_travel_receipts_only'}};
 const version=defineVersion(indicators,manifest);
 return freeze({DOMAINS,INDICATORS:indicators,MANIFESTS:{[manifest.model_version]:manifest},VERSIONS:{[version.model_version]:version},defineVersion,freeze});
});
