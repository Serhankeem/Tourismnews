# Step 19.5 — 메뉴 구조 및 탐색 UX

기준: PR #59 병합 main `f82e75d275fa2959e320c49701e1376d8f492c15`. UI/내비게이션 독립 변경이며 게시 승인·실제 발행·운영 배포를 포함하지 않습니다.

## 탐색 구조

상단 **한국 관광의 날씨는?**는 기존 뉴스와 같은 disclosure입니다. 같은 클래스·열기/닫기·포커스·Escape·바깥 클릭·콘텐츠 폭 측정 기반 모바일 전환을 재사용합니다. 두 드롭다운은 하나씩 열립니다. 버튼은 네이티브 Enter/Space를 쓰고 ArrowDown은 첫 하위 링크로 이동합니다. Escape는 하위 메뉴부터 닫고 버튼에 포커스를 돌려준 뒤, 다음 Escape에서 모바일 전체 메뉴를 닫습니다. Tab으로 그룹을 벗어나면 닫힙니다.

| 하위 메뉴 순서 | 유지한 URL | 화면 |
| --- | --- | --- |
| 월간 진단 | `#weather` | 공식 통계 기반 부분 모니터·종합 판정 보류·현재 미발행 상태 |
| 가상 시뮬레이터·공식 관측 | `#weather-simulator` | 기존 가상 실험과 공식 관측·차트 |
| Macro Monitor 상세 | `#macro` | 기존 Macro Monitor 한 화면 |

상단 관광지표 메뉴도 `#macro`를 가리킵니다. 별도 Macro 페이지를 만들지 않습니다. 뉴스·데일리 브리핑·리서치와 `#sources` 기존 진입을 유지합니다. 세 화면의 내부 보조 탐색은 위 순서를 공유하며 현재 링크에 밑줄·굵기·`aria-current=page`를 표시합니다. 모바일에서는 간결하게 줄바꿈합니다.

월간/시뮬레이터는 기존 weather 컨테이너에서 선택한 본문만 표시하고 화면 제목·설명·breadcrumb을 함께 바꿉니다. 두 본문을 동시에 노출하지 않습니다. Macro는 기존 페이지를 그대로 사용합니다. 메뉴 전환·해시 직접 진입·새로고침·뒤/앞으로 가기는 동일한 라우팅 경로를 사용합니다.

홈 Key Indicators·소개·Data Sources에서 Market Weather 전체를 미검증 시뮬레이션이라고 하던 표현을 고쳤습니다. 월간 진단은 공식 통계 기반 부분 모니터, 시뮬레이터는 가상 실험이며 실제 종합 관광시장 날씨 판정은 제공하지 않는다고 구분합니다.

### 발견한 UX 문제와 최소 보완

모바일에서 첫 드롭다운을 열고 다음 버튼을 누르면, 포인터로 생긴 focusout이 먼저 패널을 접어 클릭 지점을 이동시켰습니다. 포인터/터치에서는 click 처리 시 닫고, 키보드 focusout은 즉시 닫도록 공유 핸들러를 보완했습니다. touch 호환 mouse 이벤트까지 처리한 뒤 포인터 상태를 해제하며 다음 keydown은 키보드 경로로 전환합니다.

접근성 자동 검사에서 기존 시뮬레이터의 `/ 100` 보조 글자 대비가 부족했습니다. `ui-2.css`의 해당 글자 opacity만 0.85→1로 바꿨습니다. 점수·색상 체계·계산식·슬라이더/초기화는 바꾸지 않았습니다.

## 검증

- Python 전체 회귀 **743개 통과** (`python -m unittest discover -s tests -v`). 기존 Gate·발행 경계·Macro·TOURGO·뉴스·리서치 포함.
- 새 `weather-navigation.smoke.cjs`: 320/390/768/1024/1440에서 드롭다운 Enter/Space/ArrowDown/Tab/Escape·포커스 복귀/그룹 이탈·포인터 및 모바일 터치 전환·외부 클릭·활성 표시·세 화면 분리·직접 URL/새로고침/뒤·앞으로 가기·미발행 상태·시뮬레이터 세 입력/초기화·621개 Macro/두 Macro 진입 경로 검사.
- axe-core의 WCAG 2 A/AA 및 2.1 AA: 다섯 폭 × 열린 두 드롭다운과 세 화면, **25개 상태 검사에서 자동 위반 0개**. 수동 스크린리더 검사 완료를 의미하지 않습니다.
- 기존 공개 브라우저 회귀 **9종**: home, header-weather-v22, market-weather-v2, market-weather-public-preservation, navigation-research-v21, briefing-observation, reports, newsroom, macro-tourgo.
- 기존 공개 월간 reader 합성 테스트도 유지합니다. 명시적 합성 원고/승인으로만 읽기·잘못된 계약/만료·본문 변조 차단을 검사하며 실제 r2 공개 JSON은 생성하지 않습니다. 새 탐색 1종+기존 9종+기존 합성 reader 1종으로 **브라우저 11종**을 구분합니다.
- 기존 테스트 변경은 늘어난 메뉴 링크/새 라벨·열기 동작·긴 한국어 제목 뒤 실제 보조 탐색 위치·측정 기반 compact 모드에 맞춘 선행조건입니다. 기존 기능 검사를 제거하지 않았습니다.

`node --check site/currentourism.js`, `git diff --check`와 정적 보존 대조도 수행합니다. 실제 Pages 업로드나 운영 Actions를 실행하지 않습니다. 검증 산출물/로그는 Git 밖 `/workspace/work/weather49-step19-5/`에 보존합니다.

## 보호 조건

Publication Gate·weather_release·월간 공개 reader·공식 관측/Macro 구현·pipeline allowlist·통계/운영 정책을 기준 main과 해시 대조했습니다. 기존 시뮬레이터 함수도 동일합니다. `site/data`, `collector_state`, `.github/workflows`, 승인 플래그 변경은 없습니다. 기존 621개 Macro를 읽으며 새 통계 활성화·승인 범위 확대를 하지 않았습니다. 실제 r2/비공개 원고·원장·검토자 기록·게시 핀을 화면이나 저장소에 넣지 않습니다. 월간 공개 파일은 0개입니다.

Draft PR 검수·별도 병합/배포 판단을 기다립니다. 기존 main push는 자동 배포를 유발할 수 있으므로 승인 전 병합하지 않습니다. 롤백이 필요하면 이 UI 커밋만 되돌리며 운영 데이터와 승인 상태를 과거로 되돌리지 않습니다.

## 검수용 스크린샷

아래 이미지는 로컬의 **기존 공개 데이터와 미발행 화면**입니다. 실제 9월호 r2 원고·수치의 월간 콘텐츠를 담지 않습니다. 합성 콘텐츠 화면은 이 스크린샷에 포함하지 않았습니다.

| 화면 | 데스크톱 1440 | 모바일 390 |
| --- | --- | --- |
| 상단 드롭다운 | [보기](screenshots/dropdown-1440.png) | [보기](screenshots/dropdown-390.png) |
| 월간 진단 미발행 | [보기](screenshots/weather-1440.png) | [보기](screenshots/weather-390.png) |
| 가상 시뮬레이터·공식 관측 | [보기](screenshots/weather-simulator-1440.png) | [보기](screenshots/weather-simulator-390.png) |
| 기존 Macro Monitor | [보기](screenshots/macro-1440.png) | [보기](screenshots/macro-390.png) |
