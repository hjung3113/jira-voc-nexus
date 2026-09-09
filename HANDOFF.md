# Jira VOC Nexus handoff — 2026-09-10

## 현재 상태

- OSS/VOC 재사용 연구 게이트는 [docs/OSS_RESEARCH.md](docs/OSS_RESEARCH.md)와
  [docs/TOOLING_DECISION.md](docs/TOOLING_DECISION.md)에 반영되어 충족됐다.
- 현재 기준선은 Python 3.9+ stdlib/SQLite, 기존 OpenCode native CLI, 그리고 네 공유
  local skill(`orca-cli`, `orchestration`, `voc-slice`, `voc-workflow`)이다.
- Jira connector, Promptfoo, Pydantic AI/LangGraph, n8n/Activepieces runtime은
  설치·도입하지 않았다. `atlassian-python-api==5.0.4`는 실제 ACL/auth/server flavor가
  생긴 뒤 검토할 향후 후보이며, Promptfoo는 저장된 결과용 선택적 future eval이다.
- CLI는 파일 입력 local proposal scaffold이며 production ingress, Jira ACL/adapter,
  webhook, RAG, write reconciliation을 제공하지 않는다. evidence가 있는 event마다
  OpenCode process 하나를 실행하고, evidence가 없으면 provider process를 생략한다.
- 개발 워커의 GLM 경로는 기존 Z.AI 인증의 OMP `zai/glm-5.3`이며 OpenRouter를
  선택하지 않는다. 운영 OpenCode는 별도로 지정할 사내 provider/model을 사용한다.
  credential·endpoint·private config는 저장소에 넣지 않는다.

## 검증과 다음 단계

- bounded review fixes([docs/REVIEW.md](docs/REVIEW.md) 5개 판정) 반영 후 최종 검증을
  coordinator가 2026-09-10에 실행했다.
- `python3 -m unittest discover -s tests -v`: 11/11 통과. 관리 설정 감지 선행 거부,
  실패 스트림 fail-closed, 미승인 provider 거부 회귀 테스트를 포함한다.
- fixture CLI smoke(`python3 -m nexus --event fixtures/event.json --corpus
  fixtures/corpus.json --state .local/coordinator.sqlite3`): exit 0, `dry_run: true`,
  `published: false`, 라벨 `possible-duplicate`, 근거 PAY-42로 정상 출력.
- `python3 scripts/doctor.py`: 환경 체크 전부 true. doctor는 read-only 설계라
  provider 인증은 확인하지 않았다(`provider_auth_checked: false` 유지).
- `git diff --check` 통과, 루트/`docs/` 상대 링크 전부 확인. 이 검증 세트를 통과한
  상태로 coordinator가 commit/push했다.
- 실제 Jira/provider 연결은 정보와 ACL 계약이 확보된 뒤 별도 slice다.

## 변경 경계

이번 문서 pass는 문서만 갱신했으며 runtime/tests/fixtures와 [docs/REVIEW.md](docs/REVIEW.md)는
변경하지 않았다. 현재 commit에 runnable Jira adapter나 새 required dependency를 넣지
않고, future integration slice에서만 read-only Port와 승인된 write lifecycle을 검토한다.
