# 장 점검용 가상 원고

`python -m drift <원고>`(장 점검)의 입력과 정답지예요. 원고 한 장에서 패키지 버전, 설치 명령, API 호출, 시점 민감 문장을 뽑아 각각 판정해요. 정답지는 모델에 보내지 않고 채점에만 써요.

| 원고 | 정답지 | 성격 |
|---|---|---|
| [chapter03.md](chapter03.md) | [chapter03.expected.json](chapter03.expected.json) | 개발용 — LangChain·OpenAI·pandas·PyTorch·ROS 2 |
| [chapter05.md](chapter05.md) | [chapter05.expected.json](chapter05.expected.json) | 홀드아웃 — numpy·scikit-learn·pydantic·matplotlib·requests |
| [chapter07.md](chapter07.md) | [chapter07.expected.json](chapter07.expected.json) | 블라인드 — 파이프라인을 보지 않은 OpenAI Codex CLI가 작성, 라벨은 목표 환경 실행으로 확인 |

```bash
.venv/bin/python -m drift samples/chapter03.md --agent --out out/ch03
.venv/bin/python experiments/eval.py out/ch03/result.json samples/chapter03.expected.json
```

개정 흐름 데모에 쓰는 가상 기술서는 [`sample-book/`](../sample-book/)에 따로 있어요.
