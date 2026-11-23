# 장 점검 — Liner 에이전트 정답지 평가 (2026-11-22, 최종 코드)

## chapter03 (`out/exp/inspect-agent-03b`)
```
✅ ros2-humble-latest       기대 YELLOW   결과 YELLOW
✅ tested-date-vs-model     기대 YELLOW   결과 YELLOW (보너스)
✅ pip-pins                 기대 RED      결과 RED
✅ langchain-llmchain       기대 RED      결과 RED
✅ langchain-lcel           기대 GREEN    결과 GREEN
✅ openai-chatcompletion    기대 RED      결과 RED
✅ pandas-append            기대 RED      결과 RED
✅ torch-cuda-amp           기대 YELLOW   결과 YELLOW
✅ vivo-sdk                 기대 UNKNOWN  결과 UNKNOWN
{
  "accuracy": "8/8",
  "detected": "8/8",
  "false_alarm_on_green": [],
  "fabricated_on_unknown": [],
  "bonus_hit": [
    "tested-date-vs-model"
  ],
  "extra_items": [],
  "citations_valid": "7/7",
  "quotes_found": "7/7",
  "escalated": 1,
  "errors": [],
  "seconds_total": 92.49,
  "seconds_extract": 20.53,
  "item_seconds_max": 54.38,
  "served_models": {
    "claude-opus-5.5": 15,
    "claude-sonnet-5.5": 9
  }
}
```

## chapter05 (`out/exp/inspect-agent-05c`)
```
✅ python38-claims          기대 YELLOW   결과 YELLOW
✅ requests-get             기대 GREEN    결과 GREEN
✅ numpy-float-product      기대 RED      결과 RED
✅ sklearn-boston           기대 RED      결과 RED
✅ pydantic-v1-api          기대 YELLOW   결과 YELLOW
✅ mpl-seaborn-style        기대 RED      결과 RED
✅ numpy-sum                기대 GREEN    결과 GREEN
✅ labx-lidar               기대 UNKNOWN  결과 UNKNOWN
{
  "accuracy": "8/8",
  "detected": "8/8",
  "false_alarm_on_green": [],
  "fabricated_on_unknown": [],
  "bonus_hit": [],
  "extra_items": [],
  "citations_valid": "10/10",
  "quotes_found": "10/10",
  "escalated": 0,
  "errors": [],
  "seconds_total": 48.37,
  "seconds_extract": 17.38,
  "item_seconds_max": 17.07,
  "served_models": {
    "claude-opus-5.5": 9,
    "claude-sonnet-5.5": 11
  }
}
```

## chapter07 (`out/exp/inspect-agent-07b`)
```
✅ numpy-latest-claim       기대 YELLOW   결과 YELLOW
✅ sensor-features          기대 GREEN    결과 GREEN
✅ distance-simps           기대 RED      결과 RED
✅ camera-antialias         기대 RED      결과 RED
✅ map-from-numpy-matrix    기대 RED      결과 RED
✅ calibration-cg-tol       기대 RED      결과 RED
✅ noise-randomstate        기대 YELLOW   결과 YELLOW
✅ planar-numpy-matrix      기대 YELLOW   결과 YELLOW
✅ spatial-rotation         기대 GREEN    결과 GREEN
✅ navigation-shortest-path 기대 GREEN    결과 GREEN
✅ internal-policy-adapter  기대 UNKNOWN  결과 UNKNOWN
{
  "accuracy": "11/11",
  "detected": "11/11",
  "false_alarm_on_green": [],
  "fabricated_on_unknown": [],
  "bonus_hit": [],
  "extra_items": [
    "practice-packages-pip-install"
  ],
  "citations_valid": "13/13",
  "quotes_found": "13/13",
  "escalated": 0,
  "errors": [],
  "seconds_total": 53.35,
  "seconds_extract": 21.47,
  "item_seconds_max": 19.43,
  "served_models": {
    "claude-opus-5.5": 15,
    "claude-sonnet-5.5": 8
  }
}
```

## 도구 사용 통계
```json
{
 "items": 30,
 "tool_calls": {
  "liner_search": 28,
  "submit_verdict": 31,
  "run_example": 13,
  "liner_deep_research": 1
 },
 "submit_rejected": 1,
 "evidence_basis": {
  "-": 8,
  "official-citation": 21,
  "observed-failure": 1
 },
 "fixes_by_run_status": {
  "text": 3,
  "ok": 11,
  "needs_api": 3,
  "context": 1
 },
 "served_models": {
  "claude-sonnet-5.5": 27,
  "claude-opus-5.5": 36
 },
 "agent_router_cost_usd": 0.996
}
```
