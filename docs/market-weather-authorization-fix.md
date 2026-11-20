# VOL.01 authorization 실패: Candidate 전송 공백 호환

기준 main: `a5c721a50c68ffa80c8a34872d5dd980096a098e`.
실제 [실패 Run 44681861640](https://github.com/Serhankeem/tourismnews/actions/runs/44681861640)의 job `136106907030` 로그와 artifact `14604878245/result.json`을 분석했습니다.

## 확인된 실패 조건

기존 `from_environment()`는 등록된 Candidate Secret에 `base64.b64decode(..., validate=True)`를 바로 적용합니다. 실제 등록된 두 Secret을 읽기만 하는 [PR CI 44685680736](https://github.com/Serhankeem/tourismnews/actions/runs/44685680736/job/136119317536)에서 다음 안전 코드만 기록했습니다. 값·원고·원자료·키는 출력하지 않았습니다.

- `monthly_legacy_candidate_transport_invalid`: 실제 Candidate Secret이 기존 strict Base64 검사에서 거부됨.
- `monthly_legacy_signing_key_format_ok`: 서명 키 형식은 기존 검사에서도 정상.
- `monthly_private_input_preflight_ok`: Candidate의 ASCII 전송 공백/줄바꿈만 제외하면 원고와 candidate SHA-256, 동결 입력·수치·통계 정의·권리·기간 검증 통과.
- `monthly_legacy_role_read_http_200` / `monthly_legacy_role_contract_ok`: 기본 GITHUB_TOKEN으로 기존 사용자 권한 API도 조회/계약 검증 성공.

공백 제거 외에 해독된 입력을 변경하지 않았는데 승인 대상 두 해시가 정확히 일치하므로, 재현된 차단 원인은 **Candidate의 전송 공백과 기존 strict Base64 처리의 비호환**입니다. API 접근권한 부족이나 서명 키 오류를 원인으로 보고하지 않습니다. 실패 Run의 원래 상세 예외는 남아 있지 않지만, 등록된 Secret에서 기존 코드의 실패 조건을 실제 CI로 재현했습니다. Secrets는 수정하지 않았습니다.

원래 artifact는 authorization/ready=false, collection not_started, previous_public_preserved=true, deployment skipped였습니다. `data_commit`/`data_committed` 필드 자체가 없으며 소스상 트랜잭션 호출 전입니다. GateError의 원인 코드가 diagnostics allowlist에 없어 `ExecutionError`/`validation_or_execution_failed`로 치환된 점도 재현했습니다. 이를 이후 별도 정기 실행의 data/live 갱신 여부와 혼동하지 않습니다.

## 최소 수정

1. Base64 transport의 ASCII 공백·탭·CR/LF만 제외하고 기존 strict 디코딩을 수행합니다. 압축 크기·포맷과 **해독된 전체 candidate SHA 및 원고 SHA**를 그대로 강제합니다. Secret 값·원본 파일·원고/수치는 바꾸지 않습니다.
2. 월간 전용 API read client가 실행 정보/사용자 권한 조회의 401/403/404/429·네트워크/비정상 응답을 고정 코드로 구분합니다. 기존 TOURGO client는 수정하지 않습니다.
3. diagnostics에 승인·입력·통계의 고정 안전 enum을 추가합니다. HTTP 본문·URL·헤더·토큰·개인 입력은 출력하지 않으며 임의 예외 문자열은 계속 generic 처리합니다. runner에는 동작 변경 없이 안전한 원인이 result.json에 남는 회귀를 추가했습니다.
4. 기존 PR test job에서 기본 GITHUB_TOKEN으로 실제 run과 권한 응답 계약을 읽기 전용 검증합니다. 운영 dispatch/Request/공개 투영은 호출하지 않습니다. 원인 조사에만 사용한 PR #64 전용 Secret 사전검사 단계는 조사 후 최종 workflow에서 제거했습니다. 최종 PR 검사는 생산 Secret을 전달하지 않습니다.

기본 토큰의 기존 역할 조회가 정상임을 확인했으므로 초기 조사판의 owner-only 정책 변경은 최종 패치에서 제거했습니다. **기존 write/maintain/admin 권한 검사·actor/triggering actor·main/코드 SHA/첫 시도/두 해시·승인 1회 방식은 유지**합니다. 서명 키 처리와 `weather_publication.py`의 수치/권리/정의/기간 검증도 원래대로 유지합니다. 새 Secret/PAT/DB/서비스/workflow/승인 단계가 없습니다.

## 검증 및 운영 경계

기존 780개를 포함하는 전체 회귀와 신규 8개 검사를 실행합니다. 원고/통계·해시 변조, 권리 위반, 승인 누락, 재실행, HTTP 오류, 원인 코드 보존, 저장 전 실패 차단, 기존 발행본·RSS/Research/Macro/TOURGO·Pages 경계 검사를 유지합니다. 정상화는 전송 계층에만 적용하며 단위·통계 정의·최종성·공식 XLSX 독립 재검증 범위를 바꾸지 않습니다.

실제 VOL.01 공개 JSON·승인 기록 생성, Secrets 변경, 운영 Actions 실행, 실패 Run Re-run, 병합·배포를 하지 않았습니다. 원고·동결 입력과 운영 데이터·통계 승인 범위는 보존합니다. 코드/CI 통과가 실제 발행 성공은 아닙니다. 검수·병합 및 별도 사용자 승인 후 **새 main workflow_dispatch**를 사용해야 합니다. 기존 두 해시를 유지하고 실패 Run을 재실행하지 않습니다.

공식 API 근거: [Get a workflow run](https://docs.github.com/en/rest/actions/workflow-runs#get-a-workflow-run), [사용자 저장소 권한 조회](https://docs.github.com/en/rest/collaborators/collaborators#get-repository-permissions-for-a-user). CLI/문서만을 당시 기본 토큰의 증거로 사용하지 않았으며 실제 PR CI의 읽기 결과로 호환성을 확인했습니다.
