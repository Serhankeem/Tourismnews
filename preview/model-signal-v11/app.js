'use strict';
const labels={kto_inbound:'방한 외래관광객',kto_tourism_receipts:'일반여행수입'},tones={rain:'비',cloudy:'흐림',partly:'구름 조금',sunny:'맑음'};
const text=(id,value)=>{document.getElementById(id).textContent=value;};
fetch('/result.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('preview_unavailable');return r.json();}).then(r=>{
 text('version',r.model_version+' · 통계 기준월 '+(r.reference_period||'미확인')+' · 편집·게시 승인 없음');
 const periods=r.latest_observation_periods||{};
 for(const [id,p] of Object.entries(periods)){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=labels[id];dd.textContent=p+(id==='kto_inbound'?' · KTO 공식 XLSX 자동 수집':' · TOURGO 수동 원본');document.getElementById('latest').append(dt,dd);}
 if(r.status!=='observed'){text('score','모델 판정 유보');text('alignment','유보 사유: '+r.reason);text('missing','자료 부족 또는 검증 실패 상태에서 점수·날씨를 생성하지 않습니다.');return;}
 text('score',r.score_display+' / '+tones[r.weather]);
 text('alignment',r.alignment_reason==='last_common_official_month'?`${r.reference_period} 기준 · 방한객은 ${periods.kto_inbound}까지 갱신됐지만 일반여행수입은 ${periods.kto_tourism_receipts}까지 확인되어 마지막 공통 기준월로 진단했습니다.`:`${r.reference_period} 기준 · 두 핵심 지표의 최신월이 일치합니다.`);
 text('missing','위 최신월 이후 값은 이 입력에서 미확보입니다. 일반여행수입 2026-10 이후는 현 승인범위 밖이며 대체·추정·이월하지 않습니다.');
 for(const a of r.axes){const box=document.createElement('div'),h=document.createElement('h3'),p=document.createElement('p'),link=document.createElement('a');h.textContent=labels[a.indicator_id];p.textContent=`${a.value.toLocaleString('ko-KR')} ${a.unit} · YoY ${a.yoy_pct}% · 평활 YoY ${a.smoothed_yoy_pct}% · 백분위 ${a.percentile} · 점수 기여 ${a.contribution} · 입력 ${a.input_from}~${a.input_through} · 비교 ${a.reference_from}~${a.reference_through}`;link.textContent=a.publisher+' 원문';link.href=a.source_url;box.append(h,p,link);document.getElementById('axes').append(box);}
}).catch(()=>{text('score','모델 판정 유보');text('alignment','비공개 검수 데이터를 불러오지 못했습니다.');});
