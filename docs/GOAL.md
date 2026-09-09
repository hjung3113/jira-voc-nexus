# 현재 목표 — 2026-09-10

요청: 개요를 리뷰하고 가벼운 하네스/스킬/규칙을 자율 구성해 스캐폴드, 검증,
기록, 커밋·푸시까지 완료한다. 같은 목표를 Codex goal 기능에 등록했다.

| 완료 조건 | 확인 방법 |
| --- | --- |
| 경량 도구 선택 | `TOOLING_DECISION.md`의 후보·근거·채택/보류 이유 |
| 정적/휴리스틱 역할 분리 | `ARCHITECTURE.md`와 실제 실행 코드 |
| 스킬·규칙 설치 | `scripts/doctor.py` 성공, `CLAUDE.md -> AGENTS.md` |
| 로컬 흐름 실행 | 합성 이벤트→근거→검증된 댓글/라벨 proposal CLI |
| 실패/중복 보호 | unittest의 ACL·근거·실패 스트림·replay 검증 |
| 독립 리뷰 | Orca Grok 4.6 high 또는 GLM 5.3 high 결과와 조치 기록 |
| 문서·인계 정리 | `INDEX.md`, 운영 계약, 루트 `HANDOFF.md` |
| 저장·공유 | 검증된 변경 커밋과 origin 푸시 일치 확인 |

추가 게이트: 재사용 가능한 오픈소스의 실제 소스·라이선스·의존성·통합 비용 조사를
`OSS_RESEARCH.md`에 기록했고, 그 결과를 반영한 현재 도구 결정은
`TOOLING_DECISION.md`에 확정했다. 현재 commit에는 Jira/Promptfoo/framework
의존성이나 runnable adapter를 추가하지 않으며, 실제 ACL/auth/server flavor가 생길 때
별도 integration slice에서 재평가한다.

실제 Jira 게시/배포, 실제 사내 provider 품질 검증은 연동 정보가 확보된 다음 슬라이스다.
현재 목표에서 합성 fixture 통과를 운영 완료로 간주하지 않는다.
진행 결과와 남은 작업은 `HANDOFF.md`에만 갱신한다.
