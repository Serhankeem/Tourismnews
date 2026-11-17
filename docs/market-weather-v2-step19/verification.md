# Step 19 검증 결과

2026-11-17(KST), 기준 main `62550a6d` / PR #58 병합 확인.

## 자동 검사

| 검사 | 결과 |
| --- | --- |
| 전체 Python 회귀 | `python -m unittest discover -s tests -v`: **741개 통과** |
| 최종 발행 경계 집중 검사 | `test_weather_release.py`: **22개 통과**. 위 전체 실행 이후 추가한 경로 보호·디렉터리 교체 실패 2개 포함, 중복 합산하지 않음 |
| 기존 Publication Gate | `test_weather_publication.py`: **33개 통과**, 전체 회귀에도 포함 |
| 새 공개 reader 합성 브라우저 | 320/390/768/1440, 키보드·히스토리·출처·미발행/만료/변조/미승인 필드 및 계열 차단, **통과** |
| 공개 reader axe | 같은 네 폭, WCAG 2 A/AA + 2.1 AA 자동 위반 **0개** |
| 실제 r2의 보호된 private Preview | 같은 네 폭, 본문 다섯 섹션·키보드·axe·게시 차단·새 세션 API 거절 **통과** |
| 기존 공개 브라우저 회귀 | home, header-weather-v22, market-weather-v2, market-weather-public-preservation, navigation-research-v21, briefing-observation, reports, newsroom, macro-tourgo **9종 통과** |
| 정적 검사 | `git diff --check`, Python compileall, JS syntax 검사 **통과** |

전체 회귀 741개와 추가 안전성 2개로 서로 다른 Python 검사 **743개**가 확인됐습니다. 집중 검사 22개·Gate 33개는 이 수와 중복됩니다. 새 브라우저 1종, 실제 private Preview 1종, 기존 9종을 구분합니다. 접근성 결과는 자동 검사 범위이며 수동 스크린리더 검수 완료를 뜻하지 않습니다.

첫 전체 실행에서 선택적 precommit 인자를 일반 TOURGO 트랜잭션의 기존 테스트 seam에도 전달하는 호환성 문제를 발견했습니다. 월간 파일이 없는 경로는 기존 Store 호출을 그대로 유지하도록 수정했고, 위 전체 회귀 재실행에서 모두 통과했습니다. 기존 브라우저 검사도 새 내비게이션 라벨/시뮬레이터 경로와 현재 활성 TOURGO 선행조건을 반영하여 재실행했습니다. 운영 데이터나 시뮬레이터 계산을 바꿔 검사를 맞추지 않았습니다.

## 양성/음성 리허설

- 양성: 명시적 합성 원고·숫자·별도 합성 편집/게시 승인으로 실제 Gate→격리 stage→로컬 bare Git 트랜잭션→재복구→Pages→업로드 guard를 검사했습니다. 실제 원격 ref나 Actions를 사용하지 않았습니다. 반복 발행 no-op, 다른 collector의 침범 롤백, 원고 수정·철회·만료·카탈로그 오류·추가 자산·push 직전 철회·조립/업로드 변조의 차단을 확인했습니다.
- 음성: 실제 r2는 기존 승인 해시와 일치하며 편집/통계/계약 호환성 검사를 통과했습니다. 게시 기록 누락으로 `publication_approval_missing`이 발생하고 투영 함수 호출 **0회**, 실제 공개 파일 생성 **0개**, stage 전체 해시 무변경을 확인했습니다.
- 실제 원고·핀·승인 기록·감사 보고·스크린샷은 저장소 밖 `/workspace/work/weather49-step19-rehearsal/`에만 있습니다. 공개 저장소에는 합성 fixture를 사용하는 코드와 값 없는 검증 요약만 추가합니다.

## 운영 보존과 병합 후 CI

- main은 `62550a6d`이며 기존 merge-triggered `test` 검사들, Macro transaction, Deploy transaction의 성공을 GET으로 확인했습니다. 일부 RSS transaction은 조회 당시 pending/waiting이었습니다. 이 과업에서 운영 Actions를 dispatch/rerun/cancel하지 않았습니다.
- 병합 후 기존 운영 수집이 갱신한 data/live `1a5f8862`를 별도 디렉터리에 읽기 전용 복구했습니다. **621개 Macro 값과 정정 이력은 동결 snapshot `8c8e7ad6`과 일치**합니다. 일부 KTO 관측의 `last_collected_at` 및 원장 수집 메타데이터는 기존 운영 수집으로 갱신돼 있으므로 전체 원장이 byte-identical하다고 주장하지 않습니다.
- 최신 snapshot 검증은 뉴스 118건, 내부 기사 131건, 리서치 138건, Macro 621개, 신규 decimal/aviation 관측 0개입니다. 월간 공개 파일은 없습니다. 이는 조회 시점 값이며 원격 브랜치를 이 과업에서 갱신한 결과가 아닙니다.
- `site/data`, `collector_state`, `macro_sources.json`, `operating_policy.json`, `.github/workflows`의 Git 변경은 없습니다. TOURGO 범위/승인·기존 뉴스/리서치·시뮬레이터 계산·신규 계열 비활성 상태를 유지했습니다. `site/`의 변경은 검토용 브랜치의 통합 코드이며 운영 홈페이지에 적용하지 않았습니다.

## 남은 조건

별도 게시 승인/신뢰 핀, 보호된 authority 공급·철회 책임, 실제 공개 화면의 편집/접근성 검수, 코드 병합 및 Production 배포 승인, 정정/회수 절차가 남아 있습니다. 이번 리허설을 실제 발행 승인이나 Production 성공으로 취급하지 않습니다. 상세 발행 경계·운영 준비·롤백 절차는 [README](README.md)에 있습니다.
