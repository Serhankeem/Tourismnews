# VOL.01 authorization 실패 분석 및 최소 보강

기준 main: `a5c721a50c68ffa80c8a34872d5dd980096a098e`. 실패 [Run 44681861640](https://github.com/Serhankeem/tourismnews/actions/runs/44681861640), job `136106907030`, artifact `14604878245`의 실제 로그와 `result.json`을 확인했습니다. 실패 Run을 재실행하지 않았고 Secrets를 변경하지 않았습니다.

## 확인된 사실과 확정할 수 없는 부분

- 로그의 토큰 권한은 Actions read / Contents write / Metadata read입니다. 원고·candidate 입력 해시, checkout main SHA, 첫 workflow_dispatch, 저장소·actor/triggering actor는 제공된 실행 정보와 일치합니다. 두 Secret과 pipeline token은 로그에 마스킹된 상태로 존재합니다. 존재한다는 사실이 내용/형식이 맞다는 뜻은 아닙니다.
- 진단은 phase/failure_phase `authorization`, ready false, error_kind `ExecutionError`, code `validation_or_execution_failed`, collection_status `not_started`, previous_public_preserved true, deployment skipped입니다. `data_commit`/`data_committed` 필드 자체가 없고 코드상 트랜잭션 호출 전에 종료됐습니다. 이는 이후 별도 정기 실행의 data/live 갱신 여부를 뜻하지 않습니다.
- 재현 가능한 확정 결함은 **오류 분류 손실**입니다. 기존 diagnostics allowlist가 GateError의 원인 코드들을 수용하지 않고, TOURGO용 API client도 HTTP 오류를 하나로 합쳐 상세 실패 지점이 사라집니다. 예를 들어 해시/키 형식/권리 GateError도 모두 같은 코드로 저장될 수 있었습니다.
- 따라서 당시 오류를 특정 HTTP 403, collaborator API, 잘못 등록된 Secret, 해시 불일치 중 하나로 **확정할 수 없습니다**. 원래 예외/HTTP 상태가 기록에 없습니다. 현재 CLI로 세 endpoint(실행/저장소/사용자 권한)는 HTTP 200이며, 이 CLI credential은 당시 기본 GITHUB_TOKEN과 다릅니다. 이를 당시 토큰 성공 증거로 사용하지 않습니다.
- 원본 로컬 `candidate.b64`를 내용 출력 없이 해독해 입력 두 해시를 확인했고 실패시각 기준 원고/동결 입력/수치/권리/TOURGO 기간 검사를 통과했습니다. GitHub Secret 실제 바이트와 일치하는지는 관측할 수 없습니다. 공식 XLSX 독립 재파싱이나 역사적 as-of 검증을 수행한 것이 아닙니다.

## 변경

1. 인증된 GitHub run 응답의 repository.owner와 actor의 ID/login을 대조하는 **개인 저장소 소유자 전용 승인**으로 한정합니다. 별도 collaborator 역할 endpoint는 발행 경로에서 제거합니다. 기존 write/maintain/admin 협업자 허용보다 좁은 정책이며 권한 완화가 아닙니다. main·실행 중·첫 시도·run ID·코드 SHA·두 해시가 담긴 실행 제목·actor/triggering actor 바인딩은 유지합니다. 임의 환경변수/문자열만으로 승인되지 않습니다.
2. 월간 전용 read client가 401/403/404/429·네트워크/비정상 응답을 고정 코드로 분리합니다. TOURGO 기존 API client와 수집 경로는 변경하지 않습니다. HTTP 본문·URL·헤더·키·원고는 오류에 출력하지 않습니다.
3. 진단 allowlist에 승인/입력/통계의 고정 enum만 추가합니다. 임의 예외 문자열은 계속 generic 처리합니다. runner의 트랜잭션/오류 처리 경계를 바꾸지 않고 실제 result.json에 안전한 원인을 보존하는 회귀를 추가했습니다.
4. Secret 복사 과정의 ASCII 공백·줄바꿈은 Base64 transport에서만 제거하며, 해독된 **원고/candidate 바이트 SHA는 그대로 강제**합니다. 서명 키는 앞뒤 ASCII 공백만 제외한 뒤 동일한 소문자 hex 64자리 규칙을 유지합니다. Secret 값 자체나 원본 파일을 수정하지 않습니다. 이 보강이 당시 원인이었다고 주장하지 않습니다.
5. 기존 PR test job에 읽기 전용 기본 토큰 계약 검사를 추가합니다. 실제 실패 Run의 metadata/owner를 읽고, 종전 collaborator endpoint의 HTTP 상태만 진단합니다. Request/authorize/public projection/운영 dispatch는 호출하지 않으며 Secrets를 주입하지 않습니다. PR에서만 실행되어 정기 RSS/Research/Macro/TOURGO의 운영 경로에 요청을 추가하지 않습니다.

## 기본 토큰의 근거와 검증 범위

공식 [Get a workflow run](https://docs.github.com/en/rest/actions/workflow-runs#get-a-workflow-run)은 Actions read를 명시하고, [사용자 저장소 권한 조회](https://docs.github.com/en/rest/collaborators/collaborators#get-repository-permissions-for-a-user)는 Metadata read 및 GitHub App token 지원을 명시합니다. 문서나 다른 credential만으로 실제 실패 토큰의 응답을 확정하지 않습니다. PR CI의 기본 GITHUB_TOKEN 읽기 검사가 현재의 실제 호환성 증거이며, 그 결과를 PR에 별도로 기록합니다. 새 PAT/Secret/승인 단계/DB/workflow는 없습니다.

## 검증과 재발행 경계

기존 780개를 포함한 전체 Python 회귀 및 신규 실패 분류·키/입력 포맷·소유자·재시도 차단·runner 저장 전 실패 보존 검사를 수행합니다. 기존 합성 발행→후속 RSS→Pages 및 무결성/권리 게이트 테스트를 유지합니다. 실제 r3 원고/입력·승인 범위·사이트·운영 데이터는 변경하지 않으며 실제 공개 JSON을 생성하지 않습니다.

패치 CI/기본 토큰 계약 검사 통과가 실제 VOL.01 발행 성공을 의미하지는 않습니다. 당시 사라진 원인은 소급 복원할 수 없습니다. 수정 검수·병합 및 별도 사용자 승인 후 **새 main workflow_dispatch**가 필요합니다. 실패 Run의 Re-run은 사용하지 않습니다. 동일 두 해시를 유지하고, 새 실행이 다시 실패하면 보존된 안전한 원인 코드에 따라 처리합니다. 기존 Secrets는 변경하지 않습니다.
