# 개발 환경과 검증

## 선택한 도구

- Python 3.9+ stdlib: 입력 정규화, lexical retrieval, proposal 검증, SQLite state,
  CLI. 현재 Jira/Promptfoo/framework 패키지는 설치하지 않고 fixture를 실행한다.
- OpenCode native CLI headless: 허용된 사내 provider가 준비됐을 때 evidence event마다
  process 하나를 수행하는 adapter. 한 process stream의 auxiliary event/title은 별도
  provider 요청으로 세지 않으며, 개발자 기본 provider 설정을 운영 설정으로 사용하지
  않는다.
- Orca CLI + orchestration: supervised 작업을 조정할 때만 사용한다.
- 프로젝트 skill 정본: `.agents/skills/`의 `orca-cli`, `orchestration`, `voc-slice`,
  `voc-workflow`; `.claude/skills`, `.opencode/skills`, `.omp/skills`는 이를 가리키는
  링크다.

전역 shell 설정, 다른 레포, 도구 버전·인증, Jira/MCP 연결은 자동으로 바꾸지 않는다.

## 설치된 것과 미설치 후보

현재 실행에 필요한 것은 Python 표준 라이브러리, SQLite, 기존 OpenCode CLI와 네 개의
공유 local skill뿐이다. `atlassian-python-api==5.0.4`는 실제 ACL/auth/server flavor가
확보된 뒤 검토할 향후 Jira adapter 후보이며 현재 설치·도입하지 않는다. Promptfoo
`0.122.2`도 저장된 결과용 선택적 eval 후보일 뿐 설치하지 않으며, pycontribs/jira,
mcp-atlassian, Pydantic AI, LangGraph, n8n, Activepieces runtime도 추가하지 않는다.

Python 3.9는 현재 scaffold의 호환성 기준이지 제품의 영구 runtime 제약이 아니다. 이후
실제 연결과 운영 근거가 다른 Python floor 또는 service lifecycle을 정당화하면 도구를
재평가한다. 실제 provider가 필요해질 때의 현재 모델 선호는 Z.AI `zai/glm-5.3`이며,
OpenRouter credential이나 private config는 저장소에 넣지 않는다.

## 검증 명령

```sh
python3 scripts/doctor.py
python3 -m unittest discover -s tests -v
python3 -m nexus --event fixtures/event.json --corpus fixtures/corpus.json --state .local/demo.sqlite3
git diff --check
```

`doctor.py`는 Python 버전, 실행 파일 존재 여부, skill/symlink와 저장소 entry file을
확인하는 read-only **환경 점검**이다. provider 인증을 확인하지 않으며 runtime이나
테스트를 대신 실행하지 않는다. unittest는 replay/ACL/실패 응답/grounding 같은
**runtime gate**이고, fixture CLI는 파일 경계의 smoke다. 둘 다 실제 provider·Jira
성공을 증명하지 않는다. 이 docs pass에서는 테스트를 실행하지 않으며, 최종 테스트
수와 결과는 coordinator가 narrow runtime review 뒤 갱신한다.

같은 event를 CLI에 다시 주면 SQLite 저장 결과를 재사용한다. event ID가 같은데
payload가 바뀌면 conflict가 나야 하며, corpus 변경은 event identity에 포함되지
않는다. 의도적 update는 새 event ID/version을 사용한다.

## 로컬과 운영의 분리

fixture corpus는 공개 가능한 합성 데이터다. 실제 VOC, token, 원문, prompt, provider
응답은 Git·개발용 외부 모델·공용 artifact에 보내지 않는다. `.local/` state와 CLI
출력은 민감할 수 있으므로 로그 수집에서 제외한다.

현재 final runtime gate와 실제 사내 연결 검증은 [HANDOFF](../HANDOFF.md)에 기록한다.
