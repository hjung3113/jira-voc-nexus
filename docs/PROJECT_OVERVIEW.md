# Jira VOC Nexus

> 실행 설계는 [아키텍처](ARCHITECTURE.md), findings와 해소안은 [리뷰](REVIEW.md),
> 진행 상태는 [HANDOFF](../HANDOFF.md), 전체 문서는 [인덱스](INDEX.md)를 참조한다.

## 제품 방향과 미래 MVP

`Jira VOC Nexus`는 사내 Jira에 접수되는 VOC를 기존 이슈, 프로젝트 위키, 관련
프로젝트 코드 지식과 연결해 triage와 조치 추천을 지원하는 봇을 목표로 한다.
다음 목록은 미래 제품 MVP의 방향이며 현재 로컬 스캐폴드가 이미 제공한다는
뜻이 아니다.

1. 신뢰된 Jira 어댑터가 새 VOC를 수신하고 제목·본문·댓글·메타데이터를 정규화한다.
2. 권한 필터를 먼저 적용한 뒤 과거 이슈 RAG에서 유사 이슈를 선정한다.
3. 해결 이슈에 기록된 실제 조치사항과 결과를 바탕으로 적용 가능한 추천을 만든다.
4. 추천별 원문 이슈와 조치 근거를 사람이 검토할 수 있게 표시한다.
5. 승인된 경계에서 Jira 댓글과 라벨을 재시도·중복 방지 규칙과 함께 반영한다.
6. 사람의 수정·승인·무시 피드백을 다시 색인해 품질을 개선한다.

미래에 연결할 지식 소스는 Jira 이슈 RAG, 프로젝트 전반 지식 위키, 관련 프로젝트
코드 그래프 RAG다. 첫 운영 연결은 실제 권한·출처 계약을 확보한 과거 Jira 이슈에
한정하고, 위키와 코드 그래프는 그 뒤에 추가한다.

## 현재 로컬 스캐폴드

현재 구현은 파일 기반 CLI와 합성 fixture corpus를 사용한다. 입력 schema를 엄격히
검사하고, corpus의 `project == event.project` 비교를 먼저 한 뒤 최대 5개까지
결정적 lexical evidence를 고른다. 이 project 비교는 순서와 누출 방지를 검증하는
**synthetic trusted-fixture boundary**이지 production authorization이나 Jira ACL
검사가 아니다. CLI는 인터넷 ingress가 아니며 webhook 서명, principal, issue
security를 확인하지 않는다.

corpus의 `text`는 출처에서 얻은 실제 remediation과 outcome을 담아야 한다. 예를
들어 무엇을 바꾸었고 어떤 결과가 관찰됐는지를 적는다. `resolved` boolean은 검색
우선순위와 fixture heuristic에 쓰는 상태 힌트일 뿐, 그 자체로 remediation이나
outcome의 사실성을 증명하지 않는다. 모든 이슈 본문과 검색 결과는 신뢰할 수 없는
데이터로 취급한다.

기본 fixture engine은 모델을 부르지 않는 결정적 demo다. `opencode` engine은
evidence가 있을 때 허용된 사내 provider 설정으로 OpenCode를 한 번만 호출하며,
semantic rerank는 현재 범위가 아니다. 모델 출력은 고정 schema·allowlist·크기
제한과 evidence 연결을 통과해야 한다. evidence가 없으면 provider를 부르지 않고
`needs-triage` proposal을 만든다.

각 로컬 이벤트는 `event_id`로 SQLite에 한 번 저장된다. 최초 입력 이벤트 JSON의
canonical SHA-256 fingerprint도 저장한다. 같은 ID와 같은 payload는 기존 결과를
재사용하며 engine을 다시 실행하지 않고, 같은 ID에 다른 payload를 주면
`StateConflictError`로 실패한다. fingerprint에는 corpus가 포함되지 않으므로
corpus나 로직 변경을 반영한 재처리는 새 event ID/version 정책이 필요하다.

## 현재 범위 밖

자동 이슈 종료, 무검토 배포, 코드 자동 수정, 권한 우회, 실제 Jira 쓰기, 실시간
webhook/queue, 운영 RAG와 피드백 색인은 현재 스캐폴드에 포함하지 않는다.
