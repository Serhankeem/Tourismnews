# VOL.01 r3 편집 검수 및 발행 준비

기준 main: `3b422cff` (작업 중 PR #61 병합을 확인해 동기화, 초기 기준은 PR #60의 `140da7be`). 이 PR은 편집 검수·비공개 Preview 준비이며 **편집 승인/게시 승인/실제 발행을 수행하지 않습니다.** 실제 원고 전문·수치 검증·diff·이미지는 Git 밖 격리 검수 패키지에만 보존합니다. 공개 저장소에는 재사용 가능한 표시 코드·합성 테스트·이 문서만 추가합니다.

## 편집본과 표시 방식

계획 발행호는 **2026년 11월 / VOL.01**, 통계 기준월은 **2026년 9월**입니다. 사용자 확인에 따라 설명은 **‘2026년 9월 검증 자료 기반’**으로 사용합니다. 기존 잠정·확정 여부 미확인 고지와 독립 공식 XLSX 재파싱/역사적 as-of 검증 미수행 한계를 유지하며 ‘확정 자료’라고 승격하지 않습니다.

r3 원고 SHA-256:

`e3ef898fcad4d4b06966c772fbe60c86fcf9d6e383c723b0dd38c7cc68d57037`

상위 r2 승인 원고 SHA-256:

`9d5ba99f6940efbe738cd43020bea4c3b83197ae2c069eb94568a0ede5973d93`

새 제목·부제와 표지/시리즈/호수/발행월·기준월/리드문을 승인 대상 원고 바이트에 포함했습니다. 기존 다섯 분석 섹션은 삭제/재작성하지 않습니다. 원값·MoM/YoY·비교월·출처 URL·자료 마감·한계 문장은 그대로이고 종합 판정은 보류합니다. 단월을 분기 전체로 바꾸거나 1인당 소비·점수·날씨 등급을 만들지 않습니다. `actual_publication_date=null`입니다.

기존 Gate가 요구하는 네 줄의 원고 헤더와 다섯 섹션 형식을 유지하기 위해 표지 정보는 첫 섹션의 고정된 앞부분에 포함했습니다. 공유 reader가 이 **동일한 원고 내용**을 표지 영역으로 올려 표시합니다. 다른 원고를 따로 승인받거나 해시 대상 밖에서 표지를 덧씌우는 방식이 아닙니다. Markdown 원본과 화면의 표시 순서 차이는 검수 대상이며 Preview가 실제 표시 구조입니다. 원본 해시는 전 내용을 대상으로 합니다.

## 필요한 최소 코드 변경

- 기존 공개 reader의 DOM 표시 부분만 `site/monthly-market-weather-view.js`로 추출했습니다. 공개 reader는 종전 계약/카탈로그/해시/만료 검사를 통과한 데이터에만 이를 호출합니다. 인증 기능이나 private 입력 경로를 공개 reader에 추가하지 않습니다.
- 표지 형식을 인식할 때만 시리즈·호수·발행호와 통계 기준을 구분해 표시합니다. 기존 r2/합성 콘텐츠는 종전 표시를 유지합니다. 과거 발행물 선택에도 통계 기준임을 명시합니다.
- 기존 loopback Preview의 `--review-manifest` 모드는 hash/입력/기간/표지를 검증한 **pending r3**만 보여줍니다. 기존 공개 reader와 같은 표시 함수/CSS를 사용하고 검산용 차트는 비공개 부록으로 둡니다. 실제 JSON 투영은 하지 않습니다.
- 기존 r2 승인 Preview는 그대로 지원합니다. 새 pending 모드와 승인 기록 입력은 함께 사용할 수 없습니다. session/Host/Origin/CSP/no-store/파일 경로 차단을 유지합니다. 승인 플래그만 바꿔 public 모드로 렌더링하는 경로는 계속 닫혀 있습니다.

Publication Gate, `weather_release.py`, 공개 v2 스키마, 운영 통계 정책과 승인 범위는 **변경하지 않았습니다.** pipeline의 정적 자산 allowlist에는 새 공유 표시 JS 이름만 추가합니다. 원고/진단 JSON/Trust는 정적 자산에 넣지 않습니다. 별도 DB/관리 페이지/스케줄러/발행 workflow를 만들지 않습니다.

## 검증 결과와 비공개 산출물

초기 main의 Python 전체 회귀 **743개 통과**, 새 r3 검증 **7개 통과**를 확인했습니다. 이후 PR #61 병합 main을 동기화해 **전체 Python 764개 통과**를 확인했습니다(기존 RSS 복구 검사와 신규 r3 검사 포함, 중복 합산하지 않음). 새 검증은 합성 원고만 사용하며 pending 유지, r2 승인 재사용 거절, 숫자/출처/해시/입력/기간/표지 불일치·미확정 발행일·가짜 승인·경로 이탈 차단을 확인합니다. 기존 Preview 서버 회귀도 재검사합니다.

실제 r3 Preview는 320/390/768/1440에서 전체 다섯 섹션·표지·통계/비교월·원문 링크·본문/차트의 같은 입력·키보드·반응형·axe WCAG 2 A/AA+2.1 AA를 통과했고 자동 위반은 0개입니다. 이미지는 비공개 검수 패키지에만 보존하며 수동 스크린리더/실기기 검수 완료를 뜻하지 않습니다. 기존 공개 월간 reader는 실제 r3 대신 명시적 합성 승인/숫자로 검사했습니다. 기존 r2 승인 Preview, 공개 reader, Macro/시뮬레이터 보존, 내비게이션, 홈, Daily Briefing, 리서치와 실제 r3까지 **브라우저 8종 통과**를 확인했습니다.

격리 패키지 `/workspace/work/weather-vol01-r3-20261119/`:

| 산출물 | 역할 |
| --- | --- |
| `candidate-01/manuscript-r3.md` | 해시 대상 원고 전문·동결 후보 |
| `manuscript-r3-review-copy.md` | 같은 초기 바이트의 검토용 편집 사본. 수정 시 원래 해시 승인 대상이 아님 |
| `candidate-01/r2-to-r3.diff`, `r2-to-r3-comparison.md` | 정확한 diff 및 변경 비교표 |
| `data-accuracy-review.md` | 원고와 분리한 수치/출처/이용조건/검증 한계 |
| `candidate-01/review-manifest.json`, `preflight-private.json` | 원고·입력 연결, pending/not_requested, 실제 발행일 null, Gate 사전 검사 |
| `screenshots/r3-1440.png`, `screenshots/r3-390.png` | PC/모바일 실제 비공개 검수 화면 |
| `publication-readiness.md` | 차단 요인과 운영자 실행 심사 순서 |

원고 해시를 고정한 후보와 원본 r2/승인 기록은 덮어쓰지 않았습니다. 기존 r2 승인 기록을 r3로 재사용하면 **`manuscript_hash_mismatch`**, r3의 승인이 없으면 **`editorial_approval_missing`**입니다. 공개 객체/JSON 생성은 0개입니다. pending manifest는 승인 기록도 Trust pin도 아닙니다.

## 현재 운영 차단 항목

1. **r3 편집 승인 없음:** 위 정확한 해시에 대한 새 사용자 승인·승인자·실제 승인시각·별도 편집 기록과 외부 editorial pin이 필요합니다. r2 승인을 승계하지 않습니다.
2. **r3 게시 승인 없음:** 편집 기록/원고/입력/계약/투영 구현 해시·기준월·r3·public revision 1·권한 범위/기한/발행 기준시각을 묶은 별도 결정과 publication pin이 필요합니다. 임시 승인자를 쓰지 않습니다.
3. **Authority 전달 미구성:** 제공된 Trust에는 기존 r2 편집 pin만 있고 게시 pin은 없습니다. 이 Codex 환경의 `MARKET_WEATHER_AUTHORITY_DIR`도 없으며, 현재 workflow에는 그 전달이나 `--monthly-release-key` 연결이 없습니다. GitHub Secret 등록 상태를 조회해 확인했다고 주장하지 않습니다. 이름만 Secret에 등록하면 완성되는 설정이 아닙니다.
4. **운영 경로 검수:** 보호된 runner의 실제 외부 읽기 전용 authority/기록 공급·소유/접근 권한·갱신/철회 책임을 운영자가 정해야 합니다. 원고의 정확한 바이트와 전체 동결 입력 bundle(manifest 및 검증 대상 파일들)도 기록이 가리키는 위치에 전달해야 합니다. 이 Codex 환경의 `/workspace/work` 파일이 GitHub runner에 존재한다고 가정하지 않습니다. 전달 경로를 정한 뒤 기록을 고정하며, 경로를 바꿔 기록 바이트가 달라지면 편집 기록 hash·게시 binding·pin도 재검증해야 합니다. 일반 정기 실행에도 기존 월간 파일의 재검증을 위한 Authority가 필요합니다. 최초 발행 키는 승인된 일회 경로에서만 넘깁니다.
5. **RSS 및 코드 동기화:** 작업 중 RSS 복구 PR #61의 병합(`3b422cff`)을 확인해 이 검수 브랜치에 반영했습니다. 로컬 편집/Preview는 RSS를 수집하지 않지만 운영 Pages는 data/live 트랜잭션을 공유합니다. `--requested none`도 due 엔진을 reconcile하므로 순수 콘텐츠 전용 배포라고 주장하지 않습니다. 병합 후 기존 Deploy 트랜잭션의 성공과 data/live 갱신은 읽기 전용으로 확인했지만, 정기 RSS 실행의 안정성·관측값/freshness와 발행 시점의 최신 main/data head는 다시 확인해야 합니다. 압축 저장 형식용 decoder를 포함한 최신 코드를 유지해야 하며 과거 main으로 되돌려 발행하지 않습니다.

기존 KTO/TOURGO 통계의 이용조건 근거를 새로 미확인 상태로 되돌리지 않습니다. 비상업·무료·광고 없음·출처 표시 및 TOURGO **2021-01~2026-09** 승인 범위를 기존 엔진으로 재검증합니다. 새 발행일 시점에도 현재 권리/유효기간을 다시 검사하며 이를 월간 콘텐츠 게시 승인으로 대신하지 않습니다. ECOS/항공 신규 계열을 쓰거나 범위를 확대하지 않습니다.

## 승인 이후의 운영자 실행 순서 — 현재 실행 금지

1. r3 전문/Preview/표지 표시·원고 hash·숫자·출처/한계를 사람 검수하고 **편집 승인과 게시 승인을 각각 명시**합니다. 수정하면 새 hash에 대한 승인이 필요합니다.
2. 실제 승인 정보를 검증해 외부 readonly 편집/게시 기록과 역할별 Trust pin을 설치합니다. `authority.json`의 record는 실제 파일을 가리켜야 하며 missing/null을 임시 승인 값으로 채우지 않습니다. 전달 경로를 보호된 기존 workflow에 연결하는 변경도 별도 검수합니다.

   발행 registry에는 실제 두 승인이 완료된 r3 항목을 등록합니다. 미발행 r2의 `publication_record=null` 항목을 함께 남기면 전체 grants 검사가 차단됩니다. r2 원본/승인 자료는 외부 보존하되 활성 발행 항목으로 승계하지 않습니다. 승인 기한·철회/만료 후 처리도 미리 정해야 하며, 현재 첫 판본 불변 계약에서 날짜만 임의 변경해 갱신할 수는 없습니다.
3. RSS 저장 복구와 최신 코드/데이터 head를 확인합니다. 재실행/코드 병합/Production 배포를 별도로 승인합니다. 이 Draft를 미리 병합해 기존 자동 배포를 유발하지 않습니다.
4. 승인된 보호 runner에서 아래 **기존 CLI 경계**를 사용하도록 연결합니다. 현재 workflow_dispatch 입력에는 월간 발행 옵션이 없으므로 단순히 RSS Actions 버튼을 누르는 것으로 실행되지 않습니다. 필요한 전달/연결은 아직 구성하지 않았으며 아래 명령을 지금 실행하지 않습니다.

```sh
python -m src.pipeline.runner run \
  --work "$RUNNER_TEMP/tourism-pipeline" \
  --output "$RUNNER_TEMP/tourism-pages" \
  --requested none \
  --monthly-authority-dir "${MARKET_WEATHER_AUTHORITY_DIR:?real protected authority required}" \
  --monthly-release-key market-weather-2026-09:1
```

기존 CLI의 main/Actions 맥락·양쪽 승인·현재 권리/기한·저장/Pages guard를 전부 통과해야 합니다. 수동으로 환경을 위조하거나 Gate를 건너뛰어 파일을 쓰지 않습니다. 기존 upload/deploy 직전 guard와 실패 시 이전 공개물 보존을 유지합니다.

5. 배포 성공 후 GitHub의 실제 deploy 성공 timestamp·code/data commit·artifact/content hash·실제 URL 내용을 확인해 **별도 배포 확인 기록**에 실제 발행일을 남깁니다. 현재 계약의 `issued_at`은 승인된 발행 기준시각이며 실제 배포 완료를 증명하지 않습니다. 이를 배포 성공일로 재사용하지 않습니다. 동결된 r3 파일을 사후 수정해 hash를 바꾸지 않습니다. 현재 `actual_publication_date`는 null이고 공개 화면에도 임의의 확정 일자를 넣지 않습니다.
6. 배포 실패·Gate 거절이면 기존 공개물과 data/live의 유효 저장을 보존하고 원인을 검토합니다. 원고/승인/입력을 바꾸면 재승인해야 하며 data/live 전체 롤백·승인 플래그 변경·강제 공개로 복구하지 않습니다. 발행이 다음 달로 밀리면 호수/계획 문구의 재검수 여부를 사용자가 판단합니다.

## 병합 후 읽기 전용 재확인

기존 Deploy 실행 `44457966850`의 실제 진단은 ready=true, collection_ok=true, deployment_status=success이며 확인한 data/live는 `8b97a0f1`입니다. 이 실행의 data_committed=false는 기존 저장 snapshot을 사용했다는 뜻이며 r3를 발행한 것이 아닙니다. 최신 공개 Macro는 621개이고 두 핵심의 기준월/비교월 원값 6개가 동결 입력과 일치합니다. 이 과업에서 해당 Actions를 수동 실행·재실행하지 않았습니다. 새 main 동기화와 이 재확인은 실제 월간 콘텐츠의 승인/공개/운영 설정을 대신하지 않습니다.
