## 📘 VIVO BOOKS가 책을 개정했어요

- **감지:** PyPI `langchain` 0.3.25 → **1.5.2** (업로드 2026-11-18)
- **감지:** PyPI `langchain-core` 0.3.61 → **1.8.4** (업로드 2026-11-19)
- **검증 환경:** `langchain==1.5.0`, `langchain-core==1.8.1` (이 목표 환경에서 실제로 실행해 확인했어요)
- 감지한 최신 버전과 검증 버전이 달라요. 설치된 버전까지 개정했고, 목표 환경을 올리면 다시 점검해요.

## 바뀐 내용

| 장 | 문제(관측) | 수정 | 근거 (Liner Search · 공식 문서) | 검증 |
|---|---|---|---|---|
| 1장 | 고정 버전 표기·옛 API 설명 | 버전 표기 2곳 동기화 · 본문 문장 2곳 | [LangChain v1 migration guide](https://docs.langchain.com/oss/python/migrate/langchain-v1) “The langchain package namespace has been significantly”<br>[What's new in LangChain v1 - Docs by…](https://docs.langchain.com/oss/python/releases/langchain-v1) “create_agent is the standard way to build agents in LangChain 1.0.…” | 설치 가능 확인(pip dry-run) |
| 3장 | 의존성 없음 | 유지 | — | — |
| 4장 | `ModuleNotFoundError: No module named 'langchain.prompts'` | 코드·설명 문단 | [What's new in LangChain v1](https://docs.langchain.com/oss/python/releases/langchain-v1) “The langchain namespace has been streamlined to focus on essential…”<br>[prompts \| langchain_core](https://reference.langchain.com/python/langchain-core/prompts) “from langchain_core.prompts import ChatPromptTemplate” | prompt \| 테스트 채팅 모델 \| 출력 파서 체인 경유 + 숨은 질문의 기대 출력 일치 |
| 7장 | `ImportError: cannot import name 'Tool' from 'langchain.agents'` | 코드·설명 문단 | [What's new in LangChain v1](https://docs.langchain.com/oss/python/releases/langchain-v1) “create_agent is the standard way to build agents in LangChain 1.0.”<br>[LangChain v1 migration guide](https://docs.langchain.com/oss/python/migrate/langchain-v1) “The tools argument to create_agent accepts a list of: LangChain…” | Seoul·Busan·Jeju 실행 + 도구 응답 변경 확인 + 처음 보는 도시의 최종 AI 답 확인 · 테스트 모델·고정 날씨 도구 |

**7장 도구 응답 변경 전후의 최종 답**
- 변경 전 `Busan: sunny, 22 C`
- 변경 후 `Busan: sunny, 22 C | verification-7cfcf89df0dc4774944f1be4c6a01f62`

## 저자 확인 필요

- [ ] 바뀐 설명 문단과 본문 문장이 책의 문체·흐름에 맞는지 확인해 주세요.
- [ ] 근거가 부족해 판단을 보류한 문장 1곳은 원문을 유지했어요.

## Liner 에이전트 조사 과정

RED는 원고에서 확인한 문제, YELLOW는 수정 권장, UNKNOWN은 판단 보류예요. 아래 ‘통과’는 제출안을 받았다는 표시예요.

<details><summary>4장 · 5단계</summary>

1. (턴 1) `liner_search` site:docs.langchain.com langchain v1 migration langchain.prompts moved langchain_core.prompts…
2. (턴 1) `run_example`  ok
3. (턴 2) `liner_search` site:reference.langchain.com langchain_core.prompts ChatPromptTemplate from_template reference
4. (턴 2) `liner_search` site:docs.langchain.com LangChain v1 simplified namespace legacy functionality moved to…
5. (턴 3) `submit_revision` RED 통과

</details>
<details><summary>7장 · 5단계</summary>

1. (턴 1) `liner_search` site:docs.langchain.com langchain v1 create_agent tools invoke messages
2. (턴 1) `liner_search` site:docs.langchain.com langchain v1 migration guide create_react_agent AgentExecutor…
3. (턴 2) `run_example`  fail · NameError: name 'uuid' is not defined. Did you forget to import 'uuid'?
4. (턴 3) `run_example`  ok
5. (턴 4) `submit_revision` RED 통과

</details>
<details><summary>1장 본문 · 5단계</summary>

1. (턴 1) `liner_search` site:docs.langchain.com LangChain v1 migration langchain.prompts moved to langchain_core.prompts…
2. (턴 2) `submit_verdict` RED 통과
3. (턴 1) `liner_search` site:docs.langchain.com LangChain v1 migration create_react_agent deprecated create_agent…
4. (턴 2) `submit_verdict` YELLOW 통과
5. (턴 1) `submit_verdict` UNKNOWN 통과

</details>

---
에이전트는 제안만 해요. 공식 문서 인용 대조와 목표 환경 실행 검증을 통과한 수정만 이 PR에 들어 있어요.
`dist/`의 개정 EPUB과 `REVISIONS.md`에 근거·검증 이력이 있어요. 병합 전까지는 저자 검토용 미리보기예요.