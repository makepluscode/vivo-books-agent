# 기획 — Liner Router·Search를 감싼 개정 에이전트 (Drift Agent)

> 2026-11-22 · 기획 후 같은 날 구현했어요(`drift/agent.py`, `--agent`). 실험 결과와 선정 근거는 [AGENT_EXPERIMENTS.md](../AGENT_EXPERIMENTS.md)에 있어요.
> 구현에서 바뀐 점: `check_symbol` 도구는 넣지 않았어요(`run_example`로 충분). 예산은 Router 10턴 · Search 4 · Search Agent 1 · 실행 5 · 제출 3이에요.

## 결론

**만들 수 있어요.** Liner Router의 Chat Completions가 OpenAI 방식 도구 호출을 공식 지원해요.
요청에 `tools`를 넣으면 응답의 `message.tool_calls`가 오고, 결과는 `role: "tool"` 메시지로 돌려주면 돼요.
그래서 **Router를 두뇌로, Search·Search Agent·격리 실행을 도구로** 묶은 에이전트를 만들 수 있어요.
확인 출처: [Chat Completions](https://liner.com/developers/docs/liner-model-api-chat-completions), [Router](https://liner.com/developers/docs/router-api).

## 지금과 무엇이 달라지나

| | 지금 (`drift/living.py`) | 에이전트 |
|---|---|---|
| 흐름 | 고정 순서: 실행 → 검색 2회 → Router 1회 → (실패 시) 재수정 1회 | Router가 다음 행동을 고름: 검색 → 실행 → 더 검색 → 수정 → 재실행 |
| 검색어·공식 도메인 | `book.json`에 사람이 미리 적음 | 에이전트가 오류 메시지를 보고 직접 정해요 → **새 라이브러리에 설정 없이 적용** |
| Search Agent | 근거가 0개일 때만 | 에이전트가 "근거가 부족하다"고 판단하면 호출(예산 안에서) |
| 수정안 검증 | 최종안 1회 + 재수정 1회 | 에이전트가 수정안을 실행해 보고 실패 메시지로 스스로 고침(최대 N회) |
| 판정 권한 | 하네스 | **그대로 하네스.** 에이전트는 제안만 하고, 반영 여부는 코드가 결정 |

심사 기준과 연결:
- **Liner 활용(20):** Router의 도구 호출, Search, Search Agent를 한 루프 안에서 동적으로 써요. "API를 순서대로 부른다"에서 "Liner가 스스로 조사한다"로 바뀌어요.
- **확장성(20):** 장마다 적던 `search_queries`·`official_hosts`가 필요 없어져요. 다른 라이브러리(ROS 2, PyTorch 등)에도 같은 에이전트를 쓸 수 있어요.

## 구조

```
                 ┌────────────── Liner Router (liner-claude-router, tools) ──────────────┐
원고 + 실행 오류 ─▶│  생각 → tool_calls → 결과 확인 → 다음 tool_calls … → submit_revision │
                 └───────┬──────────┬──────────────┬──────────────┬────────────────────┘
                         ▼          ▼              ▼              ▼
                  liner_search  liner_deep_research  run_example   check_symbol
                  (Search API)  (Search Agent API)   (bwrap 실행)  (목표 환경 조회)
                         │          │
                         └── 근거 장부(evidence ledger): 모든 결과에 s1, s2… 번호를 붙여 저장
                                                                            │
submit_revision(code, explanation, citations[{evidence_id, quote}]) ───────▶ 하네스 게이트
   ① 인용 구절이 장부의 검색 요약에 실제로 있나  ② 공식 도메인인가
   ③ 수정 코드가 격리 실행·도구 호출 검증을 통과하나  ④ 판정과 원본 실행 결과가 모순되지 않나
   → 통과: diff·EPUB 반영 / 실패: 이유를 tool 결과로 돌려주고 재시도(예산 안에서) / 예산 소진: 보류
```

### 도구 목록

| 도구 | 감싸는 것 | 입력 | 돌려주는 것 |
|---|---|---|---|
| `liner_search` | Search API `/tools/search/web` (`include_knowledge: false`) | `query`, `site`(선택) | 근거 번호·제목·URL·요약 최대 5개 |
| `liner_deep_research` | Search Agent API `/agents/search` (`stream: false`) | `question` | 답변 요약 + 근거 번호가 붙은 출처 |
| `run_example` | 기존 `probe._sandboxed` + `living.verify` | `code` | 상태(ok/fail/timeout), 마지막 오류 줄, 출력 |
| `check_symbol` | 기존 `probe.probe` | `module`, `name` | 존재 여부, 폐기 표시 |
| `submit_revision` | 기존 `citations_valid` + `verify` + `rewrite` | `verdict`, `code`, `explanation_ko`, `citations` | 통과/실패와 실패 이유 |

- 모델에는 근거 **번호**만 쓰게 하고, URL은 장부에서 붙여요. 모델이 URL을 만들어 쓸 수 없어요(지금 원칙 유지).
- 검색 결과·원고는 데이터일 뿐 명령이 아니라고 시스템 프롬프트에 명시해요. 그리고 판정 권한을 하네스에 두어 프롬프트 주입이 반영으로 이어지지 않게 해요.

### 예산과 종료 조건

| 항목 | 상한(제안) |
|---|---|
| Router 턴 | 8 |
| `liner_search` | 4회 |
| `liner_deep_research` | 1회 ($0.02) |
| `run_example` | 6회 |
| `submit_revision` | 3회 |
| 장 1회 비용 | 약 $0.05~0.15 예상 (Router 입력이 턴마다 누적, claude-sonnet-5.5 기준 입력 $2/1M·출력 $10/1M) |

상한에 닿으면 원고를 유지하고 보류 이유를 남겨요. 지금의 보류 규칙을 그대로 써요.

## 구현 방식 비교

| 안 | 내용 | 장점 | 단점 |
|---|---|---|---|
| **A. 직접 루프 (추천)** | `openai` SDK로 `tools` 루프를 약 150줄로 작성 (`drift/agent.py`) | 의존성 추가 없음, 예산·게이트·추적을 완전히 통제, 기존 캐시(Gateway) 재사용 | 루프를 직접 관리 |
| B. LangChain 1.x `create_agent` | `ChatOpenAI(base_url=Liner)` + `@tool` | "LangChain 1.x 에이전트가 LangChain 0.x 책을 고친다"는 영상 장면 | 검증 대상과 같은 라이브러리에 의존, 목표 환경과 실행 환경이 섞임 |
| C. Liner MCP | `search_web`·`search_agent`를 MCP 도구로 받고 로컬 도구 추가 | Liner MCP까지 활용 | MCP 클라이언트·인증 추가, 남은 기간에 위험 |

## 주의할 점 (문서 확인 사항)

- `liner-claude-router`에서는 `tool_choice: "required"`나 특정 함수 지정이 `400 unsupported_parameter`예요. `auto`만 쓰고, 도구 없이 끝내면 "submit_revision을 호출하라"고 한 번 되돌려요.
- 알 수 없는 요청 필드는 `400 unknown_parameter`예요. `temperature` 등은 적용되지 않아요. 그래서 결과가 매번 다를 수 있고, **캐시 재생**이 데모 안전장치로 계속 필요해요.
- 라우터가 쉬운 턴을 작은 모델(haiku 등)로 보낼 수 있어요. 응답의 `model` 필드를 추적에 남겨 화면에 보여줘요. 품질이 흔들리면 `routing_strategy: "quality"`를 검토해요(버전 별칭에서만 허용).
- Search API는 2026-11-11부터 Premium Data가 기본($2/1K)이에요. 지금 코드처럼 `include_knowledge: false`($1/1K)를 명시해요.

## 진행 단계 (제안)

| 단계 | 작업 | 비용 | 시간 |
|---|---|---|---|
| 0 | 도구 호출 스모크 테스트: `liner_search` 하나만 붙여 Router 1회 | < $0.01 | 15분 |
| 1 | `drift/agent.py` 루프·도구·예산·추적, 단위 테스트(가짜 Router) | 0 | 2~3시간 |
| 2 | 목업 7장으로 실호출 2~3회, 기존 `/living` 결과와 비교(정확도·호출 수·비용·시간) | 약 $0.3 | 1시간 |
| 3 | 웹 화면에 에이전트 추적(도구 호출 순서·근거 번호·재시도) 표시, 캐시 재생 | 0 | 1~2시간 |

**마감과의 관계:** 영상과 기획서 PDF가 아직 없어요. 에이전트는 기존 `/living` 흐름을 대체하지 않고 **옵션**(`--agent`)으로 붙이는 게 안전해요.
시간이 부족하면 0~1단계만 하고, 기획서·영상에는 "다음 단계"로 넣을 수 있어요.
