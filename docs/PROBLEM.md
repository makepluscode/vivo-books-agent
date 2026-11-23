# 문제 정의 — 저자가 직접 겪은 일

> 초안 · 2026-11-22
> 이야기: 비보북스 모두의창업 2차 도전신청서 Q2·Q3(2026-09-13 제출)에서 가져왔어요.
> 수치: 공개 예제 저장소와 PyPI 기록을 직접 측정했어요.

## 한 문장

**책은 독자 손에 닿는 순간 이미 과거가 돼요.** 저자가 고쳐도 빠뜨리는 곳이 생기고, 이미 팔린 책은 계속 옛 코드를 설명해요.

## 1. 저자가 겪은 일

저는 AI 에이전트 개발 기술서
『올라마와 오픈소스 LLM을 활용한 AI 에이전트 개발 입문』(위키북스, 공저)의 저자예요.
약 8개월 동안 원고를 쓰고 2개월 동안 편집해서 2026년 1월에 책이 나왔어요.

출간 직후 책 소개 페이지에 이런 댓글이 달렸어요.

> "책에 나온 코드를 그대로 따라 했는데 오류가 납니다. 버전이 바뀐 것 같아요."
> "라이브러리가 업데이트되면서 API가 완전히 달라졌네요. 환불 가능한가요?"

집필을 시작해서 책이 나오기까지 약 10개월이 걸렸어요. 그사이 핵심 라이브러리인 LangChain의 메이저 버전이 바뀌었어요.
저자인 저도 이 사실을 **독자 댓글을 보고서야** 알았어요.
제가 할 수 있었던 일은 고친 예제 코드를 GitHub에 따로 올리는 것뿐이었어요. 이미 팔린 책은 여전히 옛 코드를 설명하고 있었고요.
지금 쓰고 있는 두 번째 책에서도, 원고를 쓰는 사이에 핵심 라이브러리 버전이 또 바뀌고 있어요.

## 2. 숫자로 확인한 것

책의 공개 예제 저장소 [`godstale/ollama-mcp-tutorials`](https://github.com/godstale/ollama-mcp-tutorials)를 2026-11-22에 확인했어요.

| 날짜 | 일어난 일 | 근거 |
|---|---|---|
| 2025-10-17 | LangChain·LangGraph **1.0 출시** | PyPI 업로드 시각 |
| 2025-11-02 | 예제 저장소 `main` 마지막 갱신, 0.x 기준 코드 | 커밋 `b6a00a5` |
| 2026-01 | 책 출간, 독자 오류 댓글 | 저자 경험 |
| 2026-01-31 ~ 02-01 | 저자가 **이틀 동안 커밋 10개**로 1.x에 맞춰 수정. 64개 파일 변경(+2,025 / −2,229줄) | 브랜치 `feat/langchain-v1.1` (`20dde39`) |
| 2026-11-22 | 수정 브랜치가 아직 `main`에 합쳐지지 않았어요. 책 안내대로 `git clone`하면 `main`을 받아요 | `git ls-remote` |

책은 예제마다 `uv sync`로 설치하라고 안내해요. 예제 대부분은 `langchain==0.3.25`처럼 버전을 고정하고 있어요(`pyproject.toml` 25개 중 21개).
그래서 독자가 어느 길로 가든 막히는지 두 경로를 확인했어요.

**경로 A — 책대로 고정 버전 설치(`uv sync --frozen`, Python 3.14):** 7장 `01_agent_with_single_tool`이 **설치 단계에서 실패**해요.
잠금 파일의 `tiktoken 0.9.0`에 Python 3.14용 빌드 파일이 없어 Rust 컴파일을 요구하기 때문이에요.
같은 `tiktoken 0.9.0`을 고정한 잠금 파일은 26개 중 10개예요. 실제 설치 시도는 7장 예제 1개만 했어요.

**경로 B — 최신 LangChain 설치:** LangChain 1.5.2(langchain-core 1.8.4, LangGraph 1.2.24) 환경을 만들었어요.
각 예제 파일의 LangChain·LangGraph `import` 문만 실행했고, 예제 코드 자체는 실행하지 않았어요.
스크립트: [`experiments/real-book-case/check_imports.py`](../experiments/real-book-case/check_imports.py)

측정 원자료는 [파일별 import 결과](../experiments/real-book-case/import-results.json)에 있어요. LangChain 또는 LangGraph의 import가 들어 있는 Python 파일마다 하나라도 불러오기 오류가 있는지 셌어요.

| 대상 | LangChain·LangGraph 사용 파일 | import에서 실패 | 영향받은 장 |
|---|---|---|---|
| `main`: 독자가 받는 코드 | 29 | **12 (41%)** | 코드가 있는 9개 장 중 **7개 장** |
| `feat/langchain-v1.1`: 저자가 이틀 걸려 고친 코드 | 29 | **1** | 10장 `02_mcp_agent_geeknews` |

실패한 import 예시:

| 책의 코드 | 최신 환경 결과 |
|---|---|
| `from langchain.prompts import ChatPromptTemplate` | `ModuleNotFoundError: langchain.prompts` |
| `from langchain.agents import Tool` | `ImportError: cannot import name 'Tool'` |
| `from langchain.agents.react.agent import create_react_agent` | `ModuleNotFoundError: langchain.agents.react` |
| `from langchain.chains.llm_math.base import LLMMathChain` | `ModuleNotFoundError: langchain.chains` |
| `from langgraph.graph.graph import CompiledGraph` | `ModuleNotFoundError: langgraph.graph.graph` |

## 3. 그래서 드러난 문제

1. **저자는 낡은 부분을 독자보다 늦게 알아요.** 감지 수단이 없어서 독자 댓글이 첫 경보예요.
2. **알아도 직접 고치면 빠뜨려요.** 이틀 동안 64개 파일을 고쳤어요. 그런데 똑같은 `langgraph.graph.graph` 오류가 9장과 10-01에서는 고쳐졌고 10-02에는 남았어요.
3. **고쳐도 독자에게 닿지 않아요.** 수정은 별도 브랜치에만 있고, 본문 설명과 이미 팔린 책은 그대로예요.

아무도 잘못하지 않았어요. 기획부터 출간까지 수개월이 걸리는 출판 구조가 AI 라이브러리의 변화 속도를 따라가지 못하는 거예요.
그리고 이 문제는 한 번으로 끝나지 않고, 기술서마다 반복돼요.

## 4. 이 출품작이 맡는 부분

비보북스(Vivo Books)는 출간 뒤에도 본문과 예제가 계속 갱신되는 Live-Ebook을 만들어요.
구성요소는 ① 집필 자동화 도구 ② 노후화 감지 파이프라인 ③ 독자용 뷰어예요.
이번 출품작은 그중 **② 노후화 감지 파이프라인**을 Liner API로 처음 구현한 거예요.

| 문제 | Book Drift Inspector |
|---|---|
| 독자보다 늦게 앎 | 원고와 예제에서 버전에 민감한 줄을 뽑고, 최신 목표 환경에서 실제로 실행해 먼저 찾아요 |
| 무엇으로 바꿀지 찾기 어려움 | **Liner Search**로 공식 마이그레이션 문서를 찾고, **Liner Router**가 근거 번호가 붙은 코드·본문 수정안을 만들어요 |
| 직접 고치면 빠뜨림 | 모든 수정안을 다시 실행해 통과한 것만 반영해요. 통과하지 못한 항목은 보류 목록에 남겨요 |
| 독자에게 안 닿음 | 코드와 설명을 함께 고친 diff, 정오표, 개정 EPUB 미리보기를 만들어요 |

## 데모 입력

데모에는 실제 도서의 원고나 예제를 쓰지 않았어요. 같은 문제(4장 프롬프트 템플릿, 7장 도구 에이전트)를 보여 주는 가상 기술서 『날씨 도우미로 배우는 LangChain 첫걸음』을 새로 써서 공개 저장소 [`makepluscode/vivo-books-sample-book`](https://github.com/makepluscode/vivo-books-sample-book)(MIT)에 두었어요.
올라마·외부 API 대신 테스트 모델과 고정 날씨 도구(`vivo_demo.py`)를 써요. 두 예제 모두 LangChain 0.3.25에서는 실행되고, 최신 1.x에서는 import에서 멈춰요.
같은 원고가 `sample-book/`에 있고, 감시기가 이 저장소에 연 실제 개정 PR은 [vivo-books-sample-book#2](https://github.com/makepluscode/vivo-books-sample-book/pull/2)이에요. 위 41% 측정은 실제 도서의 공개 예제 저장소를 대상으로 한 별도 측정이에요.

## 한계

- Python 3.12 같은 이전 버전이라면 경로 A는 설치될 수 있어요. 경로 A는 최신 Python 기준 결과예요.
- 경로 B는 import만 확인했어요. 수정 브랜치의 커밋 메시지를 보면 실행 중 오류(runtime error)를 고친 것도 여럿 있어요. 그래서 실패 12건은 **최솟값**이에요.
- 별도 패키지(`langchain_community`, `langchain_ollama`, `langchain_tavily` 등)는 2026-11-22 기준 최신판을 설치해서 확인했어요.
