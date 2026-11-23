# 실험 → MVP 반복 기록

규칙: 매 회차 계획을 Codex(`codex exec`, 읽기 전용)에 검토받고, 지적을 반영한 뒤 실행해요. 지출 상한(자체) $10.
1차 결과: `docs/history/LINER_BENCH.md` (라우터·검색·에이전트 속도/특성).
아래 `out/` 경로는 당시 실행 위치예요. 이전 실험 산출물 원본은 작업공간 외부 보관본에 있어요.

## 2차 계획 — 원고 한 장 전체를 파이프라인으로 처리

입력: `samples/chapter03.md`(직접 만든 가상 원고, 8개 점검 항목). 정답지: `samples/chapter03.expected.json`(모델에 보내지 않음).

파이프라인(MVP 후보):
1. **추출** (liner-claude-router, JSON): 원고에서 점검 항목 목록 — 위치(절·줄), 종류(code/pip/sentence), 패키지·API, 검색어(영어).
2. **근거 수집** (Search API, 영어, 5개, Premium 끔): 항목별 병렬.
3. **판정** (liner-claude-router): RED/YELLOW/GREEN/UNKNOWN + 수정안 + 근거 번호. 출처는 모델이 쓴 URL이 아니라 **근거 번호 → Search 결과 URL**로 매핑해 강제.
4. **승격**: UNKNOWN 이거나 RED/YELLOW인데 수정안이 없으면 Search Agent로 1회 재조사 후 재판정.
5. **출력**: 정오표(Markdown), 원고 diff, HTML 보고서.

측정:
- 추출 재현율: 정답지 8개 중 몇 개를 항목으로 뽑았나.
- 판정 정확도: 정답지와 일치 수(RED/YELLOW 경계는 별도 표시).
- 오탐: GREEN 항목(LCEL)을 RED/YELLOW로 판정했는가. UNKNOWN 항목(가상 SDK)을 지어내 판정했는가.
- 출처 무결성: 표시된 URL이 모두 Search/Agent 결과에 있는가(강제 장치로 100% 기대).
- 장 전체 처리 시간(병렬), 비용(잔액 차이).
- 승격 효과: 승격 전/후 판정이 정답지에 더 가까워졌는가.

반복 횟수: 전체 파이프라인 2회(일관성 확인).

### 2차 Codex 검토 → 반영
- 정답지 기준 혼재 지적 → **목표 환경 = 점검일 PyPI 최신**으로 고정, 실제 설치(`.target-env`), 줄 범위 라벨, 날짜 모순 보너스 항목 추가.
- "URL이 있다 ≠ 뒷받침" → 인용 quote 원문 대조(`quote_found`), 목표 환경 심볼 확인·**실제 실행** 추가.

### 2차 결과 (`out/r2a~c`)
| 회차 | 정확도 | 오탐(GREEN) | 지어냄(UNKNOWN) | 인용 유효/원문 일치 | 장 전체 |
|---|---|---|---|---|---|
| r2a | 7/8 | LCEL→RED | 없음 | 14/14 · 14/14 | 100s |
| r2b | 8/8 | 없음 | 없음 | 17/17 · 17/17 | 80s |
| r2c | 8/8 | 없음 | 없음 | 18/18 · 18/18 | 84s |
- r2a 오탐 원인: 심볼 확인이 pydantic 필드(`AIMessage.content`)를 '없음'으로 오인 → 인스턴스 필드 인식 + "정적 확인 한계" 규칙 추가.
- 발견: 비공식 출처(reddit·geeksforgeeks·youtube) 인용, **수정안이 저자가 하지 않은 '테스트 완료'를 사실처럼 씀**, 같은 줄 수정안 충돌.

### 3차 반영
- 공식 도메인 검색(`site:`) + 일반 검색 병합, 공식 근거 우선 규칙.
- 저자 미확인 사실은 `[저자 확인 필요: ...]`로 남기도록 규칙.
- 원고·수정안을 목표 환경에서 **실제 실행**(ok / needs_api / context / fail), 실패 시 자기 수정 1회.
- 같은 줄 수정안 병합(merge 단계).

### 3차 결과 (`out/r3a, r3b`)
- 정확도 8/8 · 8/8, 오탐 0, 지어냄 0, 인용 14/14·18/18 원문 일치, 장 전체 94s·101s.
- r3b 인용 도메인: docs.langchain.com, docs.ros.org, pandas.pydata.org, docs.pytorch.org, github.com(openai) 등 공식 위주.
- 실행: 원고 RED 3건 모두 `fail` 재현 → 수정안 pandas `ok`, openai·langchain `needs_api`(키 단계까지 통과). torch는 실행 시 실제 FutureWarning 포착.

### 홀드아웃 (`samples/chapter05.md`, 3장 튜닝 후 작성, `out/h1`)
- numpy·scikit-learn·pydantic·matplotlib·requests — 튜닝에 안 쓴 라이브러리. 라벨은 목표 환경 실제 실행으로 사실 확인.
- 정확도 8/8, 오탐 0, 지어냄 0, 인용 15/15 원문 일치, 100s. (1회 실행)
- 누적 비용: $200.00 → $198.09 (1차 벤치 포함 약 $1.9, 장 1회 ≈ $0.29).

## 3차 Codex 검토 (`out/codex-review-3.md`) → 4차 반영
지적: bwrap 없으면 무격리 실행, 호스트 `/` 전체 노출, 심볼 조회가 격리 밖, 자원 제한 없음, 시간 초과를 needs_api로 오분류, 병합 수정안 미재검증, 실패 수정안도 diff 적용, `javascript:` 링크.
- 격리: 허용 목록 마운트(`/usr`·목표 환경만 읽기 전용, 빈 `/tmp`), `--unshare-all --clearenv`, 메모리 6GB·파일 16MB·출력 64KB 제한. **bwrap 없으면 실행 거부.** 심볼 조회도 같은 격리.
  - 시험: 무한루프→timeout, 10GB 할당→MemoryError, 출력 10MB→잘림, `importlib`로 os 우회해도 홈·`.env` 안 보임.
- 분류: `timeout` 별도, `needs_api`는 마지막 예외 클래스(openai·httpx·requests 연결/인증)로만, `context`는 조각 안에서 정의 안 된 이름일 때만.
- 문맥 의존 예제: `context`면 앞 절 코드 블록(최대 3개)을 붙여 재실행.
- 산출물: 병합 수정안 재실행, 실패·겹침 수정안은 "적용 보류" 표시, http(s) 링크만.
- 폐기 휴리스틱: docstring 전체 → 첫 문단·`.. deprecated::`·`__deprecated__`만(ndarray.shape 오탐 제거).

## 4차 — 블라인드 평가 (`samples/chapter07.md`)
- Codex가 `drift/`·`docs/`를 보지 않고 원고·정답지 작성(RED4·YELLOW3·GREEN3·UNKNOWN1, 문맥 의존 1). 라벨 10개 모두 목표 환경 실행으로 사실 확인(`RandomState`는 경고 없는 레거시라 YELLOW/GREEN 모두 허용).
- 결과: b1·b2·웹 실시간 3회 모두 **11/11**, 오탐 0, 지어냄 0, 인용 20/20·21/21·22/22 원문 일치, 109~111s.
- 회귀: chapter03 8/8, chapter05 8/8.
- 추가 항목 1(설치 안내 문장 → GREEN)은 오류 아님.

## MVP — 웹 데모 (`drift/web.py`, `drift/web.html`)
- 원고 줄이 판정 색으로 칠해지고, 항목별 단계(Liner 검색 → 목표 환경 실행 → Router 판정 → Search Agent 승격 → 수정안 실행)와 Liner API 호출 로그가 실시간으로 보여요.
- 실시간 점검(실제 호출) + **기록 재생**(API 호출 없이 이전 실행을 ×4 속도로 재생 — 데모 안전장치).

## 4차 Codex 검토 (`out/codex-review-4.md`) → 반영
- 웹: 모든 작업에 종료 보장(try/finally), 실시간 점검 접수 시 비차단 잠금(동시 요청 409), SSE `id`/`Last-Event-ID` 재개로 재연결 중복 집계 방지, 연결 끊김 시 버튼 복구, 기록에 **원고 스냅샷(source.md)** 저장, 재생 속도 1~20 제한, 재생 링크는 기록 폴더로 재구성, 실패 항목도 UNKNOWN 이벤트 발행.
- 격리: `preexec_fn` 제거 → `prlimit`(메모리·파일·프로세스 수), bwrap `/tmp` 64MB. 시험: 프로세스 500개 생성 → 실패, /tmp 160MB 쓰기 → "No space left", 10GB 할당 → MemoryError.
- 보고서: 로컬 절대 경로 제거, 수정안 메모에 실행 검증 여부를 쓰지 않게(시스템이 실행해 표시) — "검증 안 함"이라 쓰고 실제론 ✅인 모순 제거.

## 5차 — 정답지 오류 발견과 pip 설치 확인
- 웹 실시간 점검에서 3장 pip 줄이 RED로 나와 확인해 보니, **정답지가 틀렸어요**: 목표 Python 3.14에 `torch==2.1.0`·`pandas==1.5.3` 휠이 없어 설치 실패(`pip --dry-run --only-binary`). Codex가 2차 검토에서 "pip YELLOW 미확정"이라 지적했던 부분.
- 정답지 RED로 정정 → 이전 3장 결과(r2b~r4) 재채점 시 **7/8** (r2a 6/8).
- pip 항목에 **설치 시도 단계** 추가(목표 Python 기준, `--only-binary`로 설치 스크립트 실행 없음, 수정안도 동일 확인).
- 결과: chapter03 8/8 × 3(r5a, r5b, 웹), chapter05 8/8, chapter07 11/11. 인용 원문 일치 100%.
