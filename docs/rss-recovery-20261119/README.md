# 2026-11-19 RSS 반복 실패 조사 및 복구안

기준 main `140da7bef1778ba4b1d27cc964a81179b80128e8` (PR #60 병합). 운영 실행·배포·Secret/승인 변경 없이 실제 GitHub 증거를 읽고 격리 테스트했습니다. 이 문서는 복구안 심사용이며 운영 복구 완료를 선언하지 않습니다.

## 확정된 장애와 확정할 수 없는 세부 원인

**16회 모두 RSS 엔진 자체의 전체 실패가 아니라, `data/live` push 실패로 저장·배포가 중단됐습니다.** 연속 실패 run #446~#461의 실제 `pipeline-diagnostics-*` ZIP **16개 전부**와 마지막 성공 ZIP을 확보해 `result.json`을 대조했습니다. 지정된 네 실행의 transaction job 로그와 단계 결과도 읽었습니다.

16개 모두 `phase=persist`, `ready=false`, `engines.news.status=partial`, `error_kind=StoreError`, `error=data_push_failed_no_deployment`입니다. 이 오류를 내는 기존 Store 경로는 push가 0 이외로 끝난 뒤 원격 head가 여전히 기존 base인 것을 확인했을 때입니다. 충돌은 다른 오류 경로로 분리돼 있으며, 수집 timeout·검증/Gate 실패·Pages 서비스 실패를 이 원인으로 바꾸어 해석하지 않았습니다.

**용량 초과가 당시 GitHub의 실제 거절 사유였는지는 확정할 수 없습니다.** 기존 `git()`이 stderr를 메모리에서만 캡처하고 Store가 고정 오류로 버렸습니다. 지정 로그와 진단 ZIP에도 원격 거절 본문/실패 stage의 blob 크기는 없습니다. GH001·권한·보호 규칙 중 어느 것이었는지 과거 증거만으로 확정했다고 주장하지 않습니다.

다만 마지막 수락 commit의 발견 원장은 **102,851,649 bytes (98.09 MiB)**로 [GitHub가 공식 설명한 파일당 100 MiB 제한](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)에 근접했습니다. 현재 설계는 계속 증가하는 후보 원장 전체를 indented JSON 단일 blob으로 쓰고 용량 preflight도 없었습니다. 이것은 실제 측정한 저장 위험이며, **별도로** 원격 크기 제한을 모사한 local bare Git hook에서 같은 persist/push 실패를 재현하고 손실 없는 압축으로 해결했습니다. 이 재현을 과거 서버의 GH001 원문을 확보한 것으로 과장하지 않습니다.

권한/규칙이 원인이었다면 압축만으로 해결되지 않습니다. 새 진단은 해당 경우도 구분하고 실패를 그대로 유지하므로, 운영 반영 후 실제 거절 분류를 확인할 때까지 원격 push 성공을 보장하지 않습니다. 저장 실패를 성공 처리하거나 exit 1을 0으로 바꾸지 않았습니다.

## 실제 실행별 증거

| 실행 | 시작 KST | 최종 phase / ready | news | collection_ok | data_committed / data_commit | 신규 저장 기록 |
| --- | --- | --- | --- | --- | --- | --- |
| [44195998047 마지막 성공](https://github.com/Serhankeem/tourismnews/actions/runs/44195998047) | 11-18 08:04:05 | ready_for_pages / true | partial | true | true / `380be4cb` | 뉴스 2 |
| [44216241258 최초 연속 실패](https://github.com/Serhankeem/tourismnews/actions/runs/44216241258) | 11-18 10:29:51 | persist / false | partial | 미기록 | 미기록 / 미기록 | 미기록 |
| [44227500689 중간 실패](https://github.com/Serhankeem/tourismnews/actions/runs/44227500689) | 11-18 12:01:57 | persist / false | partial | 미기록 | 미기록 / 미기록 | 미기록 |
| [44448535185 최근 실패](https://github.com/Serhankeem/tourismnews/actions/runs/44448535185) | 11-19 12:01:59 | persist / false | partial | 미기록 | 미기록 / 미기록 | 미기록 |

미기록은 false/0으로 대체하지 않습니다. 기존 runner는 collection_ok와 counts/new_records 및 확정 저장 정보를 commit **이후**에 결과에 넣어서 저장 실패 시 사라졌습니다. 각 실패의 **저장 전 신규 후보 수는 복구할 수 없습니다.** 반면 해당 push가 head를 바꾸지 못한 코드 경로와 현재 원격 ref/history를 확인했으므로, 이 실패들로 새로 영속 저장된 뉴스는 0건이고 최신 원격 저장은 마지막 성공의 `380be4cb6e7d482f7aa94f65c54eb5e09d5ea37c`입니다. 이것을 아티팩트에 원래 0이 기록돼 있었다고 표현하지 않습니다.

첫 실행의 수집/저장 스텝은 11-18 10:42:57에 시작해 10:46:14 KST에 exit 1로 끝났습니다. Pages 조립은 Store.commit 다음에 있으므로 도달하지 않았고 deployment.json도 실패 ZIP에 없습니다. workflow의 `ready` 출력이 없어 upload guard/configure/upload/deploy 단계는 전부 skipped였습니다. 마지막 `Mark failed collection after preserving validated data`가 최종 job을 실패로 표시했습니다. 마지막 성공은 동일한 코드·news partial에서 저장과 Pages 배포까지 성공했습니다.

### PR #59 / #60과의 관계

마지막 성공과 16개 실패 모두 `140da7be`이며, PR #60 병합 직후부터 같은 코드로 여러 정기 실행이 성공한 뒤 11-18에 연속 실패가 시작됐습니다. 실패 시 월간 공개 파일은 없었고 monthly Gate 차단도 아닌 persist/push 오류입니다. #60의 UI 코드가 원격 push 거부를 일으켰다는 증거는 없습니다. #59가 추가한 월간 분기 역시 이 실패 경로에서 활성화되지 않았습니다. 기존 Store의 거절 상세 폐기·용량 경계 부재가 진단을 어렵게 한 점은 확인했지만, 코드 동일성만으로 외부 권한/규칙 변경 가능성까지 배제하지 않습니다.

## 데이터 영향

마지막 성공의 data/live를 읽기 전용 복구해 검증했습니다: 공개 뉴스 128건, 내부 기사 141건, 리서치 138건, 발견 후보 44,595개, Macro **621개**. 신규 decimal/aviation 관측은 0개이고 실제 월간 공개 파일은 없습니다. 이미 저장된 데이터/정정 이력의 손실이나 전체 초기화·강제 롤백은 없습니다. 마지막 성공 Pages도 이번 실패에서 교체되지 않았습니다.

다만 실패 실행에서 새로 발견한 후보는 저장되지 않았습니다. 실패 아티팩트에는 후보 원장/건수도 없어 누락량을 산정할 수 없고, RSS에서 이미 사라진 항목까지 회복 가능하다고 보장하지 않습니다. 복구 승인 후 정상 피드 제공 범위에서 재수집/중복 제거하고 freshness와 신규 건수를 확인해야 합니다. 권리 없는 archive crawling으로 보충하지 않습니다.

## 구현

### 손실 없는 저장과 상한

- `src/discovery_storage.py`: 표준 라이브러리 gzip+base64 JSON envelope. format/version, 복원 크기, SHA-256을 검증합니다. 암호화나 접근 제어가 아닙니다.
- 기존 일반 discovery JSON은 계속 읽습니다. `collector.read_json`과 `pipeline.layout.read`만 해당 이름의 envelope를 논리 JSON으로 복원합니다. 손상된 envelope는 빈 원장으로 fallback하지 않고 실패시킵니다. 실제 스키마/후보 및 기존 before 검증은 복원한 데이터에 그대로 적용됩니다.
- `Store.prepare_storage`는 8 MiB 이상 발견 원장을 stage에서 손실 없이 인코딩하고 roundtrip을 확인한 뒤 기존 checksum/fast-forward 저장을 사용합니다. 후보·제목 해시·권리/출처·최초 발견시각·기존 기록을 삭제하지 않습니다. 새 DB·LFS·히스토리 재작성·강제 push를 만들지 않았습니다.
- 모든 저장 대상 blob에 100 MiB preflight, 물리 50 MiB/논리 256 MiB 경고를 추가합니다. 복원 상한은 512 MiB이며 이를 넘으면 별도 분할 설계 검토가 필요합니다. 무한 증가를 해결했다고 주장하지 않고 경고/실패를 명시적으로 남깁니다. 공개 파일은 이 압축 형식을 사용하지 않습니다.
- 실제 마지막 저장 원장 격리 실험: **102,851,649 → 5,729,166 bytes**, 44,595개 후보의 모든 논리 필드 동일. 나머지 모든 파일은 바이트 동일, 입력 snapshot 해시도 불변, 원격 쓰기 0회였습니다.

### 저장·수집·배포 진단 분리

`store.py`는 Git stderr를 메모리에서만 분류해 blob limit / 인증·권한 / repository policy / transport / unknown 코드를 돌려줍니다. 원문·원격 URL·헤더·토큰은 로그나 아티팩트로 전달하지 않습니다. push 응답이 끊겼어도 원격 head가 해당 commit이면 저장 성공을 확인하고, head 확인마저 실패하면 `unverified`로 남겨 자동 중복 저장 여부를 단정하지 않습니다.

`runner.py`, `diagnostics.py`, `report.py`는 다음을 분리합니다.

| 정보 | 의미 |
| --- | --- |
| collection_status / collection_ok | 수집 success / partial / failed. 저장 전에 확정 |
| source_summary | 정상/실패 공급원 수, 설정된 출처 ID와 안전한 실패 분류. 메시지/URL 제외 |
| attempted_new_records | 검증한 저장 전 신규 후보 수 |
| new_records / data_committed | 원격 저장 확인 후의 건수/이번 commit 저장 여부. 수락 미확인이면 null |
| data_base_commit / data_commit | 복구한 base와 확인한 원격 저장 head. base 존재를 이번 신규 저장 성공으로 혼동하지 않음 |
| storage_status / storage_diagnostics | not_attempted/pending/committed/unchanged/failed/unverified, 파일 크기·압축·경고 |
| failure_phase / error_code | 실패 단계와 고정 오류 코드 |
| deployment_status / previous_public_preserved | Summary 단계가 실제 deploy step outcome을 기록. skipped는 이 실행이 공개물을 교체하지 않음, failure/cancelled 응답은 노출 상태 미확인 |
| operator_action / retry_required / source_recovery_required | 저장소 용량/권한/규칙/원격 확인/검증·권리/공급원/저장 후 배포 문제별 후속 검토 |

기존 workflow의 항상 실행되는 Summary가 상태를 안전하게 표시하고 result.json에도 deploy outcome을 보존합니다. 새로운 운영 workflow나 수동 실행은 추가하지 않습니다. 일반 GitHub artifact 다운로드 권한은 별도 플랫폼 정책이며, 이를 Secret 보관소로 간주하지 않습니다. Summary는 코드/상태/집계, 진단 ZIP은 여기에 확인된 commit·단계·후보/저장 구분·크기 등만 추가합니다. raw Git/provider 응답과 비공개 원고는 올리지 않습니다.

### 부분 성공의 조건

기존 RSS 수집의 partial 허용을 유지합니다. 정상 공급원의 유효 피드를 처리하고 publication_result가 failed가 아니며, 모든 discovery가 실패하지 않고 briefing/권리 투영도 실패하지 않아야 합니다. 이후 기존 데이터·중복·권리/Publication Gate 검증과 저장/Pages guard를 모두 통과해야 정상 완료입니다. 건강한 빈 피드는 실패가 아니며 신규 기사 0건도 정상입니다. `partial`이면 장애 출처와 후속 조치는 계속 표시하지만 그것만으로 전체 workflow를 빨갛게 만들지 않습니다.

전체 유효 수집 실패·검증/Gate 차단·저장 거절은 실패를 유지합니다. 전체 실패 시 기존 공개 기록을 0으로 비우지 않습니다. engine별 실패 롤백·conflict 최신 상태 복구/최대 재시도·저장 후 조립 실패의 저장 commit 보존·최신 head/권리/업로드 guard는 유지합니다. 보고에 성공처럼 보이도록 exit code를 고치는 변경은 없습니다.

## 테스트 및 운영 진입 조건

회귀를 먼저 추가하고 기존 코드에서 같은 persist/push 오류와 저장 전 진단 누락으로 **2개 red**를 확인했습니다. 이후 크기 제한 local hook, 압축 roundtrip/훼손·구형 호환, 비발견 파일 상한, 불명확 push 확인, RSS 일부/전체/빈 피드/복구/중복, briefing/권리 차단, 저장 성공·조립 실패, 안전한 Summary를 테스트합니다. 실제 GitHub 원격 push나 Actions 재실행으로 테스트하지 않습니다.

운영 반영 전에는 Draft PR/CI 검수, 저장 형식 변경과 운영 배포의 별도 승인이 필요합니다. main 병합은 기존 Actions를 자동 유발할 수 있으므로 승인 전 병합하지 않습니다. 이후 실제 push 분류·accepted head·새 저장 건수·공급원 상태·deploy outcome/freshness를 확인해야 복구 완료로 판단할 수 있습니다. 권한/규칙 문제라면 운영자가 따로 검토해야 하며 이 PR은 Secrets/권한을 바꾸지 않습니다.

**롤백 주의:** envelope를 한 번 저장한 뒤에는 구형 reader로 코드만 되돌리면 읽지 못합니다. 복구 시 decoder를 유지하는 전진 수정 또는 같은 논리 데이터를 일반 JSON으로 손실 없이 변환하는 승인된 후속 절차가 필요합니다. 변환해도 blob 한계를 넘으면 분할 설계가 먼저입니다. data/live 전체를 과거로 되돌리거나 후보를 삭제해서 해결하지 않습니다. 기존 commit/정정 이력과 최신 뉴스·리서치·Macro를 보존합니다.

실제 로그/ZIP/원본 snapshot/검증 산출물은 Git 밖 `/workspace/work/rss-recovery-20261119/`에 보존합니다. 공개 PR에는 원문 로그나 후보 원장을 넣지 않습니다. 웹 UI·통계 승인·TOURGO 범위·Market Weather Publication Gate·미발행 r2·운영 데이터는 변경하지 않습니다.
