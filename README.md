# VIVO BOOKS — 살아 있는 기술서

> **Powered by [Liner API](https://liner.com/developers/docs)** — Liner Router(도구 호출) · Search · Search Agent를 핵심 기능에 사용해요.
> 제1회 라이너 해커톤 `.EXE-THON` 출품작 · 비보랩스(VIVO LABS)

AI 기술서는 출간 직후부터 라이브러리가 바뀌어 예제가 멈춰요. VIVO BOOKS는 책 저장소를 감시하다가 새 버전이 나오면 **예제를 최신 환경에서 실행해 깨진 곳을 찾고 → Liner로 공식 근거를 찾아 코드와 설명을 고치고 → 고친 예제를 격리 환경에서 다시 실행해 검증한 뒤 → 저자에게 개정 PR**을 보내요. 반영 여부는 저자가 정해요.

## 한눈에 보기

| 보고 싶은 것 | 위치 |
|---|---|
| 실제로 보낸 개정 PR | [vivo-books-sample-book#2](https://github.com/makepluscode/vivo-books-sample-book/pull/2) — 공개 가상 기술서에 VIVO BOOKS가 연 PR |
| 설치 없이 결과 보기 | [`demo/snapshot/index.html`](demo/snapshot/index.html) — 개정 전후 비교, PR 본문, 정오표, 개정 EPUB |
| 기획서 (2쪽) | [`docs/proposal/VIVO_BOOKS_기획서.pdf`](docs/proposal/VIVO_BOOKS_기획서.pdf) |
| 문제의 근거 | [`docs/PROBLEM.md`](docs/PROBLEM.md) — 실제 도서 예제 29개 중 12개가 최신 LangChain에서 멈춘 측정 |

## 문제 — 저자가 직접 겪은 일

『올라마와 오픈소스 LLM을 활용한 AI 에이전트 개발 입문』은 2026년 1월에 나왔어요. 출간 직후 독자들이 "책대로 했는데 오류가 난다"는 댓글을 달았어요. 2026년 11월 22일에 책의 공개 예제 저장소를 확인했어요.

- 최신 LangChain으로 설치하면 LangChain을 쓰는 예제 파일 29개 중 **12개(41%)가 첫 줄 import에서 실패**해요. 코드가 있는 9개 장 중 7개 장이에요.
- 책 안내대로 고정 버전을 설치하면 Python 3.14에서는 **설치 단계부터 실패**해요(7장 예제로 확인).
- 저자가 이틀 동안 64개 파일을 고친 수정 브랜치에도 **같은 오류가 1곳 남았어요.**

## 어떻게 동작하나요

```text
책 저장소(book.json · 원고 · 예제)
   │  ① 감지: PyPI 새 버전 > 책의 고정 버전
   ▼
영향받는 장 선택 ─▶ 원본 예제를 목표 환경에서 격리 실행 ─▶ ImportError 관측
   │
   ▼  ② 개정: Liner 에이전트 (Router가 도구를 골라 반복)
┌─────────────── Liner Router (liner-claude-router, 도구 호출) ───────────────┐
│  liner_search ─▶ run_example ─▶ (실패하면 고쳐서 다시) ─▶ submit_revision     │
└──────┬──────────────────────┬──────────────────────────────┬──────────────┘
  Liner Search           격리 실행(bubblewrap)          ③ 검증: 하네스가 반영 여부 결정
  Search Agent           숨은 입력·도구 호출 관측        인용 구절이 공식 출처 검색 요약에 있나
                                                        판정이 원본 실행 결과와 맞나
                                                        수정 예제가 숨은 검사까지 통과하나
   │
   ▼  ④ 제안: 원고·예제 파일 diff, 독자 정오표, 개정 이력, 개정 EPUB → 저자에게 PR
```

| Liner API | 쓰는 곳 |
|---|---|
| **Router** `/chat/completions` + `tools` | 에이전트 두뇌. 어떤 검색어로 언제 검색할지, 언제 실행해 볼지, 언제 제출할지 정해요. 1장 같은 본문 장에서는 문장 추출과 판정을 맡아요 |
| **Search** `/tools/search/web` | 공식 마이그레이션 문서·API 레퍼런스 검색(`include_knowledge: false`) |
| **Search Agent** `/agents/search` | 검색만으로 근거가 부족할 때 1회 보강 |

신뢰 장치:
- **에이전트는 제안만 해요.** 반영은 하네스가 정해요. 모델이 쓴 URL은 쓰지 않고, 근거 번호와 실제 검색 요약 속 인용 구절만 인정해요.
- **공식 출처는 패키지 메타데이터(Project-URL)에서 정해요.** 장마다 검색어나 도메인을 적지 않아도 돼요.
- **모델이 만든 코드는 bubblewrap 격리 안에서만 실행해요.** 네트워크·홈·`.env`·환경변수를 막고 메모리·파일·프로세스를 제한해요.
- **숨은 검사로 꼼수를 막아요.** 7장은 처음 보는 도시와 도구 응답 변경, 최종 AI 답을, 4장은 숨은 질문의 정확한 출력과 `prompt | 모델 | 파서` 체인 경유를 확인해요.
- **근거나 실행 검증이 부족하면 원고를 유지하고 보류 이유를 남겨요.**

## 직접 실행하기

요구 사항은 Linux, Python 3.12+, `bubblewrap`이에요.

### 1. 기록 재생 — Liner 키 없이

공개 PR #2를 만든 실행의 Liner 응답 20건(Router 13건·Search 7건)을 재생하고, 예제와 설치 명령은 지금 환경에서 다시 실행해요.

```bash
DRIFT_DEMO=1 scripts/setup.sh                           # .venv(도구)와 .target-env(목표 환경: LangChain 1.5.0)
.venv/bin/python -m drift.watch --replay-demo           # 감시 → 개정 → 로컬 PR 초안·EPUB
.venv/bin/python -m drift.web --packaged --port 8774    # http://127.0.0.1:8774/living#snapshot
```

결과는 공개 PR #2와 [`demo/snapshot/`](demo/snapshot/)의 원고·예제 파일·EPUB 장 내용까지 같고, 실행마다 새로 만드는 검사 표식과 날짜만 달라요. 출력 경로의 `artifacts/`에 `pr.md`, `reader.html`, `preview.epub`, `manuscript.diff`, `revision.json`이 생겨요.

### 2. 실제 감시 — Liner 키와 GitHub 권한 필요

```bash
cp .env.example .env                                    # LINER_API_KEY 입력 — 키는 커밋하지 않아요
.venv/bin/python -m drift.watch --repo makepluscode/vivo-books-sample-book --once --dry-run   # PR 없이 브랜치·본문만
.venv/bin/python -m drift.watch --repo makepluscode/vivo-books-sample-book --once             # 새 버전이면 PR
.venv/bin/python -m drift.watch --repo makepluscode/vivo-books-sample-book --interval 600     # 10분마다 감시
```

같은 원고와 검증 환경의 PR이 이미 열려 있으면 건너뛰어요. 책 한 권 개정에 Liner 호출 20~25회, 약 $0.3~0.4가 들어요.

### 3. 장 점검 — 원고 한 장의 여러 항목 판정

```bash
.venv/bin/python -m drift samples/chapter03.md --agent --out out/ch03     # report.html · errata.md · manuscript.diff
.venv/bin/python experiments/eval.py out/ch03/result.json samples/chapter03.expected.json
```

### 테스트

```bash
.venv/bin/python -m unittest discover -s tests          # 92개, Liner 호출 없음
```

격리 실행 환경(`bwrap`과 `.target-env`)이 없으면 예제를 실제로 실행하는 테스트 49개는 건너뛰어요.

## 저장소 구조

```text
.
├── drift/                  VIVO BOOKS 에이전트 (Python 패키지)
│   ├── watch.py            ① 감지 · ④ 제안 — 책 저장소 감시, 개정 브랜치·PR
│   ├── living.py           개정 흐름 — 영향 장 선택, 격리 실행 검증, 정오표·리더·EPUB
│   ├── agent.py            ② Liner 에이전트 — Router 도구 호출(검색·실행·제출) 루프
│   ├── liner.py            Liner API 클라이언트(Router·Search·Search Agent)와 호출 기록
│   ├── probe.py            목표 환경 확인과 bubblewrap 격리 실행
│   ├── pipeline.py         장 점검 — 원고 한 장의 항목 추출·판정
│   ├── report.py           장 점검 보고서·정오표·diff
│   ├── web.py              로컬 웹 데모(/living 개정 흐름, / 장 점검)
│   └── __main__.py         장 점검 CLI (python -m drift)
├── sample-book/            데모용 가상 기술서 — 공개 저장소 vivo-books-sample-book과 같은 내용
├── demo/
│   ├── liner-record.json   공개 PR #2를 만든 실행의 Liner 응답(재생용)
│   ├── release-event.json  drift.living 단독 실행용 로컬 릴리스 이벤트
│   └── snapshot/           설치 없이 보는 심사 자료
├── samples/                장 점검용 가상 원고와 정답지
├── tests/                  자동 테스트(Liner 호출 없음)
├── experiments/            실험 스크립트와 원자료
├── docs/                   문제 정의, Liner API 가이드, 실험 기록, 기획서
└── scripts/                환경 설치
```

각 폴더의 README에 자세한 안내가 있어요: [`sample-book/`](sample-book/README.md) · [`demo/snapshot/`](demo/snapshot/README.md) · [`samples/`](samples/README.md) · [`experiments/`](experiments/README.md) · [`docs/`](docs/README.md)

## 검증 결과

**데모 — 공개 가상 기술서 개정** ([PR #2](https://github.com/makepluscode/vivo-books-sample-book/pull/2))

- PyPI `langchain` 0.3.25 → 1.5.2를 감지했고, 목표 환경 LangChain 1.5.0에서 검증했어요.
- 1장 버전 표기·설치 명령·안내 문장 4곳, 4·7장 코드와 설명, 예제 파일 2개를 고쳤어요. 3장은 그대로 유지했어요.
- 근거가 부족한 1장 문장 1곳은 원문을 유지했어요. PR 브랜치의 예제는 LangChain 1.5.0에서 그대로 실행돼요.

**개정 흐름 — 고정 경로 vs Liner 에이전트** (2026-11-22, 이전 목업, 실호출 12회, 총 $0.96) · [`docs/AGENT_EXPERIMENTS.md`](docs/AGENT_EXPERIMENTS.md)

| 경로 | 성공 | 장 1회 | 비고 |
|---|---|---|---|
| 고정 경로 (claude / gpt router) | 5/5 | 14~28초 | 장마다 검색어·공식 도메인 설정 필요. 설정이 없으면 `KeyError`로 실패 |
| **Liner 에이전트** (claude / gpt router) | **7/7** | 19~47초, Router 약 $0.08~0.17 | 검색 설정 없는 장 포함. 제출 전 1~4회 실행 시험 |

**장 점검 — 여러 항목 판정 정확도** (직접 만든 가상 원고, 정답지는 모델에 보내지 않음) · [`docs/AGENT_EXPERIMENTS.md`](docs/AGENT_EXPERIMENTS.md)

| 원고 | 성격 | 라이브러리 | 고정 경로 (11/17) | **Liner 에이전트** (11/22) | 오탐·지어냄 | 인용 원문 일치 | 장 1회 (고정 → 에이전트) |
|---|---|---|---|---|---|---|---|
| `chapter03` | 개발용 | LangChain·OpenAI·pandas·PyTorch·ROS 2 | 8/8 × 3회 | **8/8** | 0 · 0 | 100% | 96~112초 → 92초 |
| `chapter05` | 홀드아웃 | numpy·scikit-learn·pydantic·matplotlib·requests | 8/8 | **8/8** | 0 · 0 | 100% | 113초 → 48초 |
| `chapter07` | **블라인드**(Codex가 파이프라인을 보지 않고 작성, 라벨은 실제 실행으로 확인) | numpy·SciPy·Pillow·NetworkX + 내부 SDK | 11/11 | **11/11** | 0 · 0 | 100% | 109초 → 53초 |

판정에 사용한 근거는 공식 문서 인용 21건과 목표 환경에서 관측한 실패 1건이에요. 별도 인용 대조에서 비교한 인용문 30건이 검색 요약과 모두 일치했어요. 3장 pip 줄은 정답지가 처음에 틀렸어요(YELLOW → 실제 설치 실패로 RED). 고친 정답지로 다시 채점하면 이전 고정 경로는 7/8이었고, 설치 확인 단계를 넣은 뒤 8/8이 됐어요.

## 한계

- 표본이 작아요. 개정 흐름은 LangChain API 변경 사례이고, 장 점검은 장 3개·27항목이에요(에이전트는 장마다 1회 측정). 모두 Python 라이브러리예요.
- "인용 원문 일치"는 검색 결과 요약에 그 구절이 있다는 뜻이에요. 원문 페이지 전체를 확인했다는 뜻은 아니에요.
- 다른 책에 적용하려면 `book.json`에 장별 라이브러리와 기대 출력을 정하고, 실행 환경과 테스트 데이터를 마련해야 해요.
- 감지는 PyPI 폴링으로 해요. GitHub 웹훅 수신, 병합 후 유통·POD는 아직 연결하지 않았어요.
- 검증은 이 컴퓨터의 목표 환경 버전으로 해요. PyPI 최신과 다를 수 있고, 그 경우 PR에 두 버전을 모두 적어요(예: PyPI 1.5.2 · 검증 1.5.0).

## 기존 결과물과 신규 작업

| 구분 | 내용 |
|---|---|
| 기존 | 기존 코드는 가져오지 않았어요. 비보랩스의 기술서 집필·검수 경험과, 저자가 직접 겪은 출간 후 예제 오류 사례를 문제 정의에만 참고했어요. |
| 신규(해커톤 기간, 2026-11-16~) | `drift/` 전체(장 점검, 개정 흐름, Liner 에이전트, 격리 실행, 보고서·EPUB, 웹 데모), 가상 기술서와 장 점검용 가상 원고·정답지, 평가·벤치·실험 스크립트, 실험 기록 |

데모용 가상 기술서([`sample-book/`](sample-book/), 공개 저장소 [`vivo-books-sample-book`](https://github.com/makepluscode/vivo-books-sample-book))는 이번에 새로 쓴 원고·예제예요. 실제 출간 원고와 그 예제 저장소의 코드는 쓰지 않았어요. 7장 r1 예제의 ReAct 프롬프트 형식만 LangChain(MIT)의 공개 예시를 따랐고, 원 저작권 고지를 [`THIRD_PARTY_NOTICES.md`](sample-book/THIRD_PARTY_NOTICES.md)에 함께 배포해요. 장 점검용 원고 `samples/chapter07.md`는 블라인드 평가를 위해 OpenAI Codex CLI가 작성했어요.

## 라이선스

[MIT](LICENSE) © 2026 VIVO LABS
