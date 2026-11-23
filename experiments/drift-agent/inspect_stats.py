"""장 점검 에이전트 실행(result.json)의 도구 사용·거절·근거 종류 통계."""
import json
import sys
from collections import Counter

tools, basis, rejected, fixes, models, cost = Counter(), Counter(), 0, Counter(), Counter(), 0.0
items = 0
for path in sys.argv[1:]:
    r = json.load(open(path))
    for p in r["items"]:
        a = p.get("agent")
        if not a:
            continue
        items += 1
        for s in a["steps"]:
            tools[s["tool"]] += 1
            if s["tool"].startswith("submit") and not s.get("accepted"):
                rejected += 1
        basis[p["verdict"].get("evidence_basis") or "-"] += 1
        if p["verdict"].get("fix"):
            fixes[(p.get("fix_run") or {}).get("status", "text")] += 1
        models.update(m for m in a["served_models"] if m)
    cost += sum(t.get("cost_usd") or 0 for t in r["trace"] if t.get("api") == "agent-inspect")
print(json.dumps({"items": items, "tool_calls": dict(tools), "submit_rejected": rejected,
                  "evidence_basis": dict(basis), "fixes_by_run_status": dict(fixes),
                  "served_models": dict(models), "agent_router_cost_usd": round(cost, 3)}, ensure_ascii=False, indent=1))
