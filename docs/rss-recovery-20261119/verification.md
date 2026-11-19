# 검증 기록

기준 main `140da7be`. 운영 Actions/원격 data/live push/배포 없이 검사했습니다.

| 검사 | 결과 |
| --- | --- |
| 수정 전 장애 재현 | 새 회귀 2개 모두 red: local hook push 거절의 persist 실패 및 collection_ok 진단 누락 |
| 수정 후 장애 집중 검사 | `test_pipeline_recovery.py` **14개 통과**, 전체 실행에도 포함 |
| 전체 Python 회귀 | `python -m unittest discover -s tests -v`: **757개 통과** |
| 기존 Pipeline | 충돌 시 최신 복구·중복/no-op·권리 재투영·collector 격리·저장 후 조립 실패·Pages guard 포함, 전체 회귀 통과 |
| Market Weather | 기존 Publication Gate 33개·월간 발행 경계 22개를 포함한 전체 회귀 통과, 실제 게시 승인/실제 공개 파일 생성 없음 |
| 실제 snapshot 격리 검증 | 발견 후보 44,595개 **모든 필드 동일**, 원장 102,851,649→5,729,166 bytes. 나머지 모든 저장 파일 바이트 동일·입력 해시 불변 |
| 데이터 정합성 | 뉴스 128 / 내부 기사 141 / 리서치 138 / Macro 621 / 신규 ECOS·항공 0 유지 |
| 정적 검사 | Python compileall, git diff --check 통과 |

새 14개는 테스트 fixture와 local bare remote만 사용합니다. GitHub 100 MiB 제약은 작은 동일 구조의 제한 hook으로 모사하며, 실제 GitHub로 초과 파일을 push하지 않았습니다. 손실 없는 인코딩 후 동일 hook을 통과하고, 저장한 snapshot 재복구와 checksum/논리 검증까지 확인합니다. source recovery 검사는 정상+실패 RSS, 전체 실패에서 기존 내부/공개 기사 유지, 정상 빈 피드, 복구·중복 없음 및 compressed ledger 재읽기를 포함합니다. 성공/부분/전체 실패와 저장/배포를 독립적으로 검사합니다.

## 실제 증거 보존

17개 ZIP(연속 실패 16개+마지막 성공)을 실제 다운로드해 result.json을 파싱했습니다. 16개 실패는 전부 `persist / ready=false / news=partial / data_push_failed_no_deployment`입니다. 지정 네 실행의 transaction 로그도 원문을 별도 보존했습니다. public PR에는 원문/원장·credentials·서명된 임시 다운로드 URL을 넣지 않습니다.

| run | diagnostics artifact ID | 다운로드 ZIP SHA-256 |
| --- | --- | --- |
| 44195998047 | 14380067019 | `d55ea1a038554af2545c11b4412e72764c1ef6ee3a5ed300334c1928bf92c132` |
| 44216241258 | 14388594847 | `e9b0bb3854f50d444752e541206e36d339fac860a98285c6784baf3330475210` |
| 44227500689 | 14394396668 | `d40d2408ee8f01c7736f84354c4f8beb3e5218d1c7d1a87104b94871e8800758` |
| 44448535185 | 14495237438 | `6d388497df98e8360a4fa95ae6a657e16696d5e2ffb2e04e80c26e7074991897` |

원본 ZIP은 로컬 격리 디렉터리에 보존했습니다. 기존 진단에 Git push stderr와 실패 시 blob이 남지 않아 과거의 GH001/권한/규칙 등 세부 사유를 확인했다고 주장하지 않습니다. 재현한 용량 초과 경로와 16회 모두에서 확정된 push 실패를 구분합니다.

## 운영 전 확인

PR/CI·압축 저장 형식·호환 decoder 및 롤백 제약을 검수하고 운영 반영을 별도로 승인해야 합니다. 기존 main push는 운영 실행을 유발할 수 있으므로 Draft 상태에서 병합하지 않습니다. 승인 후 실제 오류 분류/원격 head·저장 신규 건수·provider 상태·Pages outcome/freshness를 확인해야 장애 복구 완료로 판단합니다. 복구 전 누락된 RSS 항목의 전체 복원이나 원격 push 성공을 이번 로컬 검사만으로 보장하지 않습니다.

원인·시각·운영 후속·형식 변경과 보존/롤백 제약은 [README](README.md)에 있습니다. 운영 데이터·정정 이력·TOURGO 승인·뉴스/Market Weather 권리 게이트·미발행 r2·홈페이지는 변경하지 않았습니다.
