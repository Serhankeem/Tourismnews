# Phase 2-A — Model Indicator Source Audit

2026-11-23 KST. PR #65 병합 후 main `5d1dbdc5`를 기준으로 한 **사전 연구 보고서**다. 운영 모델·수집·게시 승인이 아니다. 문서는 기존 [18개 확장 후보](../market-weather-indicator-expansion-plan.md)를 같은 순서로 빠짐없이 다룬다.

## 결과

- 원본 재확인 **5/18개 후보**, 해당 월별 관측 **348개**. 과거 확보 기록만으로 완료 판정하지 않았다. 보유 원본에 대한 재검증이며 최신 원본을 새로 수집한 것은 아니다.
- 즉시 추가 확인 가능한 후보 **5개**: 출국 공개 projection 검토와 ECOS4개의 원표/정의 대조다. 권리·인증이 모두 끝났다는 뜻이 아니며 항공은 별도 허락 심의가 먼저다.
- 권리 추가 확인 **12개**, 기존 코드가 확인된 ECOS 인증 경로 심의 **4개**(중복 3개). 권리12에는 이미 확인한 공공누리/카탈로그 허락의 적용범위·가공 제약 확인도 포함한다. 법적으로 사용 불가 12개라는 뜻이 아니다.
- 새 통계 원본 다운로드·인증 API 요청·운영 활성화 **각 0건**. 상관계수·신규 점수·가중치·설명력 개선 수치는 만들지 않았다.

## 전체 비교 매트릭스

데이터와 권리는 독립 열이다. `verified_existing_evidence`는 **보유 원본과 기존 검증 결과의 현재 재확인**이며 전기간 독립 원표/권리/운영 준비 완료를 뜻하지 않는다. `access_blocked`는 정상 다운로드 절차 미완료도 포함하며 통계 부존재 판정이 아니다.

| 후보 | 영역 | 데이터 상태 | 권리 상태 | 적합성/주요 차단 요인 | 우선순위 |
| --- | --- | --- | --- | --- | --- |
| C01 국민 해외출국 | 관광수요 | `partially_verified` | `existing_scope_confirmed` | 기존 원본 XLSX 제공/확보 후 해시·행/정의 대조 | P1 |
| C02 내국인 국내여행 횟수 | 관광수요 | `source_identified` | `rights_pending` | 전국 월표·가중치·반기/연간 발표의 월별 가용 시점 및 권리 확인 | P2 |
| C03 내국인 국내여행 숙박일수 | 관광수요 | `source_identified` | `rights_pending` | 설문·코드북의 숙박일수와 전국 월표를 확인; 임의 환산/보간 금지 | P2 |
| C04 외국인 관광 카드소비 | 관광소비 | `access_blocked` | `rights_pending` | 정상 UI에서 두 목표월 파일·필터 제공, 카드사 내부 분석/가공/재배포 조건 확인 | P2 |
| C05 내국인 외지인 관광 카드소비 | 관광소비 | `access_blocked` | `rights_pending` | 공식 전국 합계 유무·카드사 표본/추정·업종 범위와 정상 다운로드 조건 확인 | P2 |
| C06 국내여행 지출액 | 관광소비 | `source_identified` | `rights_pending` | 세부 월표 원본과 공표 시점·배율·가중치·이용조건 확보 | P3 |
| C07 전국 국제선 운항편수 | 공급 | `verified_existing_evidence` | `rights_pending` | 공동 통계 파일 내부 분석/반복 다운로드/수치·증감 공개 조건과 빈티지·교차검증 확인 | P1 |
| C08 국제선 공급좌석 | 공급 | `source_identified` | `conditional_catalogue_permission` | 공식 다운로드 파일과 정확한 조건 제공; 카탈로그 허락을 실제 파일에 연결 | P2 |
| C09 관광숙박업 가용 객실수 | 공급 | `source_identified` | `conditional_no_derivatives` | 목표가 등록 객실 구조인지 실제 가용 공급인지 결정. 가공 공개 조건 확인 | P3 |
| C10 숙박업 생산지수 | 산업활동 | `verified_existing_evidence` | `research_permitted_publication_pending` | KOSIS 동일 업종/불변 원계열/2020 기준 전기간 대조; 가공 공개 권리 및 장기 인증 승인 확인 | P1 |
| C11 예술·스포츠·여가 생산지수 | 산업활동 | `verified_existing_evidence` | `research_permitted_publication_pending` | KOSIS 동일 업종/불변 원계열/2020 기준 전기간 대조; 가공 공개 권리 및 장기 인증 승인 확인 | P1 |
| C12 숙박업 월별 피보험자 | 산업활동 | `source_identified` | `rights_pending` | 숙박업 세부 산업코드/월표·가입 범위·공표일·이용조건 확보 | P2 |
| C13 원·달러 월평균 환율 | 거시경제 | `verified_existing_evidence` | `bok_attribution_permission_confirmed` | 이미 성공한 70개월 인증 기록·실제 Summary 보존 확인, 현재 키 목적/만료 점검; 별도 공표2개월 외 68개월 대조/산식 및 운영 정책 검토. 불필요한 재실행 요구하지 않음 | P1 |
| C14 숙박서비스 CPI | 거시경제 | `verified_existing_evidence` | `research_permitted_publication_pending` | K02 원작성 수준값 대조; 12/18·12/31 개편 실제 발표 후 새 코드/연결표 심사. 자동 연결 금지 | P1 |
| C15 한국은행 기준금리 | 거시경제 | `source_identified` | `bok_attribution_permission_confirmed` | 정상 공개 변경일 원표·월 대표값/변환·API 코드 선택. API면 별도 조회 승인 | P3 |
| C16 여행비 지출전망 CSI | 시장심리 | `source_identified` | `bok_attribution_permission_confirmed` | 전국 여행비 세부항목 원표·단위/척도·과거 월표/권리 연결; 수준/차분 적합성 검토 | P2 |
| C17 소비자심리지수 CCSI | 시장심리 | `source_identified` | `bok_attribution_permission_confirmed` | 전국 CCSI 공식 장기 원표·표/코드·개편 이력 확보, 여행비와 추가 기여 비교 | P3 |
| C18 숙박·음식점업 기업경기 BSI | 시장심리 | `source_identified` | `bok_attribution_permission_confirmed` | 전국 해당 업종의 연속 월표 존재와 코드 확인; 없다면 후보 제외, 광의 지표로 대체 금지 | P2 |

## 보고서 구성

- [18개 상세 메타데이터](candidate-dossiers.md): 기관·원표/항목·단위·주기·기간·공표·접근·권리·자산·위험·역할·후속 작업. [JSON 매트릭스](candidate-matrix.json)는 같은 내용을 기계 판독할 수 있게 한다. 운영 등록부가 아니다.
- [우선5개 심층 검증](priority-five.md): 실제 원본/품질, 독립 대조의 범위, 반복 수집·이용조건과 모델 한계.
- [확보 로드맵·운영자 액션·Phase2-B](roadmap.md): 자동화 개발보다 원표·정의·권리를 먼저 해결한다.
- [공식 근거·현재와 기존 확인 범위](sources.md): 출처 URL 및 확인 방법·시점.

## 중요한 판정

1. **숙박 생산지수**는 산업 활동의 우선 검토 후보지만 숙박·음식점 합계/명목/계절조정 자료로 원표 대조를 대체할 수 없다. **여가 생산**은 관광 외 지역민 활동까지 포함하는 대리다.
2. **항공 운항**은 화물기 포함 운항 활동이고 공급좌석이 아니다. 70개월 파일의 연속성은 확인했으나 전기간 독립 대조·공동 재이용 조건은 미완료다.
3. **환율**은 BOK 작성 통계의 출처표시 조건 이용허락 근거가 있다. 남은 것은 이미 성공한70개월 인증 근거/실제 Summary 보존 확인과 현재 키 범위·원표·산식·운영 심의이며 권리를 막연한 미확인으로 되돌리지 않는다.
4. **숙박 CPI**는 가격/비용 환경이다. 2025 기준 개편은 공식 공지상 2026-12-18/31 예정이며 기준년/품목/가중치가 달라질 수 있다. 발표 완료를 가정하거나 2020·2025 계열을 자동 연결하지 않는다.
5. **국민여행조사**는 월별 조사와 월별 공표가 다르다. **등록 객실**은 월별 가용 공급이 아니다. **카드소비**는 정상 다운로드 원본이 아직 없고, 간편결제·제공사 변경/소급을 분리해야 한다.

## 운영 보존·검증

현재 `data/live` `df090871`의 Macro blob을 읽기 전용 확인했다. 기존 **621개 관측**, 두 활성 계열·동일 모델 계약으로 **62.50점 / 구름 조금**, 회고 미래 prefix 오류0을 재현했다. 승인기간·권리/발행 Gate·VOL.01·모형 코드·UI·워크플로는 변경하지 않는다.

현재 원본 검증은 승인 플래그를 임시 변경한 수집이 아니다. 기존 `load_evidence`/기준 fingerprint 생성기와 항공 `snapshot`의 **오프라인 기술 파서만** 호출했으며 수집 엔진·클라이언트·모의 운영 승인도 사용하지 않았다. 기존 원본/기록을 덮어쓰지 않는다. 공개 JSON·신규 시계열·가중치·날씨 기준을 생성하지 않는다.

전체 Python 회귀와 기존 JS 모델 테스트 결과 및 메타데이터 계약 검증은 PR 본문에 기록한다. 이 PR은 문서만 추가하며 main 병합·운영 Actions·Pages 배포를 수행하지 않는다.
