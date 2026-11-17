# Step 12 — 비공개 Market Weather 진단 엔진 v0.1

[Step 11B](https://github.com/Serhankeem/tourismnews/issues/49#issuecomment-6907799300)의 제한된 방한 수요·일반여행수입 모니터를 구현합니다. `src/macro/weather_diagnostic.py`는 네트워크·수집기·스케줄·사이트와 연결되지 않은 순수 분석 함수와 외부 비공개 출력 CLI입니다. 기존 Macro 엔진/원장/시뮬레이터는 수정하지 않습니다.

## 입력 계약

`diagnose(config, archive, policy, target, cutoff, now)`는 기존 Macro 설정, `macro_archive.json`, 운영 정책, YYYY-MM 목표월, 시간대가 명시된 입력 마감/분석 시각을 받습니다. 입력은 수정하지 않습니다. CLI는 JSON 중복 키도 거부합니다.

`fixtures/weather_contract_v01.json`에는 실제 수치가 없는 9개 기존 지표의 source_id/definition/unit/frequency/publisher 계약을 고정하고 SHA-256으로 검증합니다. 핵심은 `kto_inbound`, `kto_tourism_receipts` 두 개입니다. 국적별 5개·해외출국·일반여행지급은 보조 영역에만 들어갑니다. 이 계약 밖 ECOS·항공·카드·공급좌석을 활성화해도 핵심/보조 입력에 들어가지 않습니다.

KTO는 공식 XLSX 수집 방법·검증 상태·KOGL-0·원본 해시·단위·정의를 확인합니다. TOURGO는 기존 `terms_confirmed`, `permitted`, `approved_range`, `public_pair`를 재사용해 비영리 이용조건·수집/게시 승인·기간·공식 수지 관계와 원본 provenance를 검증합니다. TOURGO의 승인 2021-01~2026-09를 확대하지 않습니다. 상대방 지급 계열은 기존 TOURGO 검증의 내부 정합성 확인에 필요하나 핵심 신호로 합산하지 않습니다.

정확한 비음수 정수·단위/주기·정의·조회/최초확인/공표 시각을 검증하고 마감 이후 빈티지·현재 진행월을 제외합니다. 잘못된 계열은 이유 코드와 함께 제외됩니다. 원공표일을 추정하지 않습니다.

## 출력 스키마

- `schema_version=1`, `methodology_version=weather-diagnostic-v0.1`
- `target_period`, `analysis_at`, `input_cutoff`, `input_hashes`(설정/원장/정책), `aligned_period`
- `mode=retrospective_current_vintage`: **항상 유지**. 원공표일 하나가 존재한다고 역사적 빈티지까지 입증되는 것은 아니므로 v0.1은 `as_of_verified` 승격 경로가 없습니다.
- `visibility=private_review_draft`, `editorial_review_required=true`, **`publication_approved=false` 고정**
- `status=partial_monitor|withheld`, `target_ready`: 두 핵심이 목표월에 있으면 부분 모니터. 공통월이 이전이면 그 월을 명시하지만 목표월은 준비되지 않은 것으로 처리. 이 필드는 웹 발행 가능/승인 플래그가 아닙니다.
- `overall_status=withheld`, `overall_reason=industry_activity_unavailable`, `industry_activity.status=missing` 고정
- `axes`: 핵심별 `period/value/unit`, `comparisons`, 비교월의 원관측, `provenance`, `warnings`
- `supporting`: 보조 지표를 같은 기준월로 분리. 핵심에 합산하지 않습니다.
- `evidence`: 최대 2개(요구 상한 3개 이하)의 원지표·대상월·제한된 방향·출처 참조. 호황/침체/회복·인과 문장 생성 없음.
- `flow_relation=mixed|not_aggregated`: 양수/음수가 엇갈리면 mixed. 상쇄 점수나 전체 시장 판단이 아닙니다.
- `warnings`: 적격성·목표월 지연·산업 부재, 축별 MoM/YoY 부재·분모 0·정정·팬데믹 기저 문맥.

원관측 value는 정수, MoM/YoY는 기존 `model.decimal_comparisons`를 재사용한 **6자리 반올림 Decimal 문자열**입니다. 원계열 MoM은 비계절조정 값이며 계절 제거/경기 전환으로 해석하지 않습니다. YoY 기준월이 팬데믹 시기인 경우 문맥 경고를 남기고, 모든 비교에 실제 분모 값을 동반합니다. 임의의 경기 임계값이나 극단값 삭제를 도입하지 않습니다. 전년값이 없거나 0이면 YoY는 null, 그 비교에 의존하는 판단은 보류합니다. 기준월 값이 없으면 0/이전값으로 채우지 않습니다.

3개월 연구 비교는 필수 입력이 아니므로 이번 v0.1에는 구현하지 않았습니다. 점수·가중치·날씨 등급·계절조정 모형도 없습니다.

방한객은 인원 통계이고 일반여행수입은 명목 US$ 국제수지 통계입니다. 서로 동일한 모집단으로 간주하거나 나누어 1인당 관광소비를 만들지 않습니다. 두 방향이 다르면 `mixed`로 설명하되 관광수지·환율·국적별 부분집합을 추가 핵심 신호로 합산하지 않습니다. 비교 기준월이 없거나 0이면 변화율을 만들지 않으며, 극단적인 변화율도 삭제·등급화하지 않고 실제 분모와 팬데믹 기저 문맥을 편집 검토합니다.

## 실행/보존

```sh
python -m src.macro.weather_diagnostic \
  --snapshot /absolute/private/read-only-data-live-copy \
  --target 2026-09 \
  --cutoff <시간대가_있는_실제_입력마감_ISO8601> \
  --output /absolute/private/new-review-directory
```

저장소 및 입력 사본 밖의 **새 출력 디렉터리**만 허용합니다. 분석 마감이 실행시각 이후이면 거절합니다. `diagnostic-private.json`만 0600 권한으로 쓰고 stdout에는 상태만 출력합니다. 운영 파일·공개 JSON·HTML·Actions를 쓰거나 실행하지 않습니다. 출력에는 실제 통계가 들어가므로 공개 저장소/웹 경로에 이동하지 마십시오.

입력 원장은 관측별 최초확인·최종수집·공표시각 및 원본 파일 해시를 그대로 참조합니다. 결과는 입력 해시와 방법론 버전으로 그림자 발행을 위한 스냅샷 식별 기반을 제공합니다. 출력 시각으로 원공표일을 채우지 않습니다. 과거 당시 원본이 없는 시점은 원장을 이전 빈티지로 재구성하지 않습니다. 과거/신규 원장을 각각 분석한 결과는 별도 보존하고 조용히 덮어쓰지 않습니다.

## 검증 범위와 한계

합성 시험과 실측 운영 원장 재현을 분리합니다. 실측은 읽기 전용 최신 `data/live`의 2026-09로 제한합니다. 이 재현은 **운영 원장 값/기록된 provenance와 공개 JSON 비교율의 일치** 검증이며 새 공식 XLSX 다운로드/파일 재파싱·과거 as-of 재현이 아닙니다. 실제 결과 파일은 저장소 밖에만 보존하고, 여기에는 값 없는 검증 요약만 추가합니다.

`verification.json`은 입력 커밋·검증 범위·통과 여부만 기록합니다. 운영 사본 621개 원관측은 읽기 전용으로 보존하고, 실제 검산 대상은 2026-09 핵심 2개 및 각각의 MoM/YoY입니다. 새로 원본 621개를 재수집·독립 검증했다는 의미가 아닙니다. 정정 시험은 이전/이후 입력 사본을 각각 분석해 기존 결과와 해시를 보존하며, 운영 원장의 빈티지 로직을 새로 구현하거나 수정하지 않습니다.

Step 13 과제: 더 엄격한 JSON Schema와 계약 변경 리뷰, 과거 원본/발표 빈티지 확보, 정정본·증거 문장의 사람 검토, 승인 범위/지연 경계의 추가 장애 시나리오, 비공개 그림자 발행 운영 및 필요 시 3개월 연구 비교입니다. 독립 원천 교차검증·계절성/기저효과 해석·공개 편집 적격성이 자동 완료된 것은 아닙니다. 신규 계열과 산업 축은 별도 승인/검증 전 사용하지 않습니다. 홈페이지 적용과 PR 병합은 사용자 검수·별도 승인 대상입니다.
