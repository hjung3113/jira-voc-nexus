# Jira VOC Nexus

`Jira VOC Nexus`의 제품 방향은 사내 Jira VOC를 과거 해결 사례와 연결해 사람이
검토할 추천 댓글과 라벨을 준비하는 것이다. 그 방향과 미래 MVP 범위는
[프로젝트 개요](docs/PROJECT_OVERVIEW.md)에 정리되어 있다.

현재 저장소는 그 제품의 **로컬 proposal 생성 스캐폴드**다. CLI가 사용자가 준
정규화 JSON 파일을 읽어 합성 corpus에서 trusted project filter와 검색·검증·중복 처리를
실행하고, 검증된 proposal을 로컬 SQLite에 저장한다. CLI는 HTTP/webhook 서버나
인터넷 ingress가 아니며, 실제 Jira 댓글·라벨 쓰기와 실제 Jira/RAG 연결은 없다.

공개 OSS/VOC 조사와 현재 채택 결정은 [OSS 조사](docs/OSS_RESEARCH.md)와
[도구 결정](docs/TOOLING_DECISION.md)에 기록했다. 현재 runtime에는 Jira connector,
Promptfoo, 별도 framework가 설치되지 않았으며, `atlassian-python-api==5.0.4`는 실제
ACL/auth/server flavor가 확보된 뒤 검토할 향후 후보다.

```sh
python3 scripts/doctor.py
python3 -m unittest discover -s tests -v
python3 -m nexus --event fixtures/event.json --corpus fixtures/corpus.json --state .local/demo.sqlite3
git diff --check
```

`doctor.py`는 Python·도구·링크·필수 entry file을 확인하는 환경 점검일 뿐이다.
unittest와 fixture CLI가 runtime 동작을 검증하는 별도 gate이며, 어느 명령도
provider 인증이나 Jira 연결 성공을 증명하지 않는다.

## 현재 실행 경계

- 기본 `fixture` engine은 모델을 호출하지 않는 결정적 합성 heuristic이다.
- `opencode` engine은 허용된 provider 설정이 있을 때 evidence가 있는 새 이벤트마다
  OpenCode process 하나를 사용한다. title 등 보조 작업으로 동일 승인 모델에 여러
  HTTP 요청이 발생할 수 있으므로 실제 횟수와 비용은 사내 연동에서 측정한다.
  semantic rerank를 별도 process로 만들지 않는다.
- OpenCode 설정은 `NEXUS_OPENCODE_MODEL=provider/model`과 prefix가 같은
  `NEXUS_APPROVED_PROVIDER`를 요구한다. `NEXUS_OPENCODE_CONFIG`가 주어지면 adapter는
  선택한 provider block만 임시 runtime config로 복사한다.
- project 동등 비교는 합성 fixture의 trusted-filter 경계일 뿐 production ACL이 아니다.
- SQLite replay identity는 `event_id`다. 최초 처리에서 이벤트 JSON의 canonical
  SHA-256을 저장한다. 같은 `event_id`와 같은 payload는 저장 결과를 재사용하고,
  payload가 바뀌면 충돌로 실패한다. corpus는 이 identity에 포함되지 않는다.
  재처리는 새 event ID/version 정책으로 구분해야 한다.

Proposal schema, 허용 라벨, 크기 제한은 [아키텍처](docs/ARCHITECTURE.md)를,
사내 provider/Jira를 연결하기 전 계약은 [운영 연결 계약](docs/INTEGRATION.md)을
참조한다.

```text
nexus/           입력 정규화·검색·판단 어댑터·검증·상태·CLI
tests/           합성 입력과 fake process 기반 회귀 검증
fixtures/        공개 가능한 합성 이벤트와 근거 corpus
scripts/         로컬 개발 도구
docs/            설계·리뷰·도구 선택·운영 연결 계약
.agents/skills/  공통 프로젝트 스킬 정본 (orca-cli, orchestration, voc-slice, voc-workflow)
AGENTS.md        공통 에이전트 규칙
CLAUDE.md        AGENTS.md 상대 링크
HANDOFF.md       현재 상태와 다음 검증
```

[문서 인덱스](docs/INDEX.md) · [목표](docs/GOAL.md) ·
[설계 리뷰](docs/REVIEW.md) · [도구 선택](docs/TOOLING_DECISION.md) ·
[OSS 조사](docs/OSS_RESEARCH.md)
