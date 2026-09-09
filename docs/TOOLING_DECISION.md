# 도구 비교와 채택 결정 — 2026-09-10

## 현재 결정

OSS/VOC 재사용 조사는 [OSS_RESEARCH.md](OSS_RESEARCH.md)에 기록했고, 연구 게이트는
충족했다. 현재 commit의 기준선은 다음 네 가지다.

- Python 3.9+ 표준 라이브러리와 SQLite runtime
- 기존 OpenCode native CLI headless 경계
- `.agents/skills/`의 네 공유 local skill: `orca-cli`, `orchestration`,
  `voc-slice`, `voc-workflow`
- 파일 입력·합성 fixture·로컬 proposal만 제공하는 현재 범위

Jira connector, Promptfoo, Pydantic AI/LangGraph, n8n/Activepieces는 설치하거나
runtime에 채택하지 않았다. Python 3.9는 현재 scaffold의 호환성 기준일 뿐 제품의
영구적인 runtime 상한/하한 결정이 아니며, 이후 실제 연결 계약과 운영 근거가 생기면
재평가할 수 있다.

| 후보 | 현재 상태 | 결정 근거와 재검토 조건 |
| --- | --- | --- |
| OpenCode native CLI | **현재 사용** | `opencode run --pure --format json --model ... --agent voc-triage` 경계를 유지한다. evidence event마다 process 하나를 시작하며, 한 stream의 auxiliary event/title을 provider HTTP 요청 수로 해석하지 않는다. |
| OpenCode SDK/`serve` | 미설치·보류 | SDK structured output은 유용하다. Python에서 `serve` HTTP를 직접 호출할 수 있어 Node bridge는 필수가 아니지만, persistent server의 health/auth/shutdown/log lifecycle이 추가된다. 그 비용이 정당화될 때만 검토한다. |
| `atlassian-python-api==5.0.4` | **향후 우선 후보, 미설치** | 실제 Jira ACL/auth와 server flavor가 없으므로 runnable adapter를 지금 만들지 않는다. 계약이 닫힌 다음 read-only `JiraPort` 뒤에 감싸고, ACL-before-search·pagination·bounded retry·reconciliation을 자체 검증한다. |
| `pycontribs/jira==3.10.5` | 미설치·보류 | 현재 3.9 scaffold에 직접 맞지 않고 object API가 넓다. Python floor 변경 자체를 금지 사유로 삼지는 않으며, 향후 runtime/adapter 요구가 생길 때 재비교한다. |
| `mcp-atlassian==0.23.1` | **runtime 거부** | agent-facing tool surface와 server/dependency/security 부담이 크다. read-only/project filter가 실제 ACL 계약을 대신하지 않으므로 제품 connector로 들이지 않는다. |
| Promptfoo `0.122.2` | 미설치·향후 선택 | 저장된 model output을 검증하는 격리 eval job에만 유용하다. 현재 골든셋·Node eval 운영 필요가 입증되지 않아 Python/runtime 의존성으로 추가하지 않는다. |
| n8n / Activepieces | 미설치·flow 참고 | 공식 support-ticket flow의 단계·dedupe·human review·branch 설계만 참고한다. template code/credentials를 import하지 않으며, 두 플랫폼 모두 deterministic step을 표현할 수 있으므로 AI가 항상 write를 소유한다고 단정하지 않는다. |
| Pydantic AI / LangGraph | 미설치·보류 | 현재 고정된 단일 proposal 흐름에 두 번째 orchestration runtime을 추가할 근거가 없다. 다일 승인 대기·복잡한 재개·직접 Python provider 호출이 실제 요구가 될 때 검토한다. |

## 실행 경계

정규화, project filter, lexical retrieval, evidence cap, proposal validation, 댓글
render, replay/dedupe는 Python이 소유한다. evidence가 없으면 OpenCode process도
시작하지 않고 `needs-triage`를 반환한다. evidence가 있는 새 event마다 OpenCode
process 한 개만 실행하며 semantic rerank를 별도 process로 추가하지 않는다.

운영 provider/model은 저장소에 넣지 않는다. 실제 사내 모델을 붙일 때의 현재 선호는
Z.AI의 `zai/glm-5.3`이며 OpenRouter를 선택한 경로로 사용하지 않는다. endpoint,
credential, ACL principal이 확보되기 전에는 provider 성공이나 Jira 운영 연결을
주장하지 않는다.

## 우선순위

1. 실제 권한으로 확보한 해결 이슈의 source-derived remediation과 outcome
2. 골든 VOC의 유사 이슈 적중률과 추천 근거 연결
3. 근거 부족 보류와 사람이 수정하기 쉬운 짧은 댓글
4. 모델 출력 실패, replay/conflict, 중복·재시도 쓰기의 재현 테스트
5. 위 자료가 필요성을 보일 때만 connector/eval/orchestration 확장

외부 모델 fallback이나 운영 자동 배포를 도구 선택으로 우회하지 않는다. 실제 Jira
댓글·라벨 쓰기는 별도의 승인된 integration slice이며 현재 결정에 포함하지 않는다.
