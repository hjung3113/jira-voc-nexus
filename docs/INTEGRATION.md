# 운영 연결 계약

현재 제공하는 것은 로컬 proposal 생성 스캐폴드다. CLI는 파일을 읽는 local
execution boundary이며 webhook server나 internet ingress가 아니다. 웹훅 서버,
실시간 queue, 실제 RAG, Jira write, feedback indexing은 아직 연결되지 않았다.

현재 Jira connector, Promptfoo, framework dependency는 설치하지 않았다.
`atlassian-python-api==5.0.4`는 실제 ACL/auth와 Jira server flavor가 확보된 뒤
검토할 향후 read-only adapter 후보이고, Promptfoo는 저장된 결과를 평가할 때만
검토할 선택적 future tool이다. n8n/Activepieces는 flow 단계·deterministic branch와
human-review 설계를 참고했을 뿐 template code나 credential을 가져오지 않았다.

## 입력·검색 계약

실제 Jira 어댑터는 인프라가 검증한 webhook과 trusted service principal을 사용해
다음 normalized event를 만든다: `event_id`, `issue_key`, `project`, `summary`,
`description`, `labels`. 현재 CLI가 이 구조를 검사하더라도 principal·ACL의 증거로
삼지 않는다.

검색 후보는 최소한 `id`, `project`, `title`, `text`, `resolved`, `url`을 제공해야
한다. `text`는 source-derived actual remediation과 outcome을 포함해야 하며 단순한
상태 설명으로 대체하지 않는다. `resolved`는 ranking/선택 힌트이지 사실성의 증명이
아니다. 실제 환경에서는 서버가 얻은 principal/issue ACL을 검색과 prompt assembly
이전에 적용하고, 검색 결과도 다시 검증한다. 댓글 공개 범위에서 읽을 수 없는
후보는 인용하지 않는다.

첫 운영 slice는 권한·출처 계약이 닫힌 과거 Jira 이슈에 한정한다. 위키와 코드
그래프는 같은 ACL, source identity, 보존 정책을 확보한 뒤 연결한다.

## Proposal·모델 계약

proposal은 `recommendations`와 `labels`만 가진다. recommendation은 `text`와
`evidence_ids`만 가지며, 최대 5개 recommendation, recommendation text 최대
2,000자, item당 1~5개의 고유 evidence ID를 허용한다. evidence ID는 이미
ACL-filtered top-5 result에 있어야 하고, label allowlist는 `needs-triage`와
`possible-duplicate`뿐이다. validator는 JSON shape, bounds, duplicate, source
membership와 보수적 lexical grounding을 검사한다.

evidence가 없으면 provider process를 시작하지 않고 `needs-triage` proposal을 만든다.
evidence가 있는 새 이벤트마다 OpenCode process 하나를 실행한다. title 등 보조 작업으로
동일 승인 모델에 여러 HTTP 요청이 발생할 수 있어 실제 횟수와 비용을 측정해야 한다. semantic rerank는 현재 별도
단계가 아니다. 모델은 Jira/search/write 도구를 받지 않는다. 모델 오류,
timeout, 잘린 stream, schema/근거 부족은 실패 또는 보류로 처리하며 공개 provider
fallback·무한 재시도·자동 고비용 승격을 금지한다.

운영 provider 설정은 배포 환경이 주입한다.

- `NEXUS_OPENCODE_MODEL`: 승인된 `provider/model` 값
- `NEXUS_APPROVED_PROVIDER`: model prefix와 정확히 일치해야 하는 승인 provider
- `NEXUS_OPENCODE_CONFIG`: 선택한 provider만 담은 runtime JSON 설정 파일

adapter는 임시 runtime config에 승인 provider 하나와 `enabled_providers`,
`small_model`, `share: disabled`, global/`voc-triage` deny-all permission 및
untrusted input을 무시하는 agent prompt만 남긴다. child에는 `OPENCODE_CONFIG`와
`OPENCODE_CONFIG_CONTENT`를 임시 runtime config로 주입하고 project/default/skill/
model-fetch/share를 비활성화한다. 실제 endpoint, model ID, credential 주입 방식,
session/log 보존과 provider containment는 실제 provider 연결 slice에서 검증한다.
현재는 임의의 값이나 인증서를 코드·문서에 넣지 않는다.

## Jira 댓글·라벨 어댑터 완료 조건

1. 검증한 proposal에 이벤트/워크플로우 버전 기반 안정적 operation key를 부여한다.
2. comment marker를 게시 전에 조회해 중복 게시를 막는다.
3. 게시 응답 유실은 `unknown`으로 기록하고 marker 조회로 확인하기 전 재게시하지 않는다.
4. comment ID와 성공 상태를 저장하고 기존 라벨을 보존하면서 allowlist만 추가한다.
5. 라벨 실패 재시도는 댓글을 재게시하지 않는다. 429/5xx는 bounded backoff,
   401/403은 운영 오류로 분리한다.
6. 다중 worker가 DB에서 작업 ownership을 원자적으로 획득한다. Jira 외부 효과와
   DB transaction 사이의 불확실성을 테스트한다.

이는 다음 integration slice의 acceptance contract이며 현재 CLI는 게시 기능이나
게시 성공 상태를 제공하지 않는다. provider와 Jira가 없는 현재 환경에서는 fixture
검증만 수행하고 연결 성공으로 보고하지 않는다.
