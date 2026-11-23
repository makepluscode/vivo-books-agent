"""out/exp/* 실행 기록을 표로 요약해요: 경로(고정·에이전트)·Router별 성공, 시간, 호출 수, 비용 추정."""
import glob
import json
import sys
from pathlib import Path

COST = {"Search": 0.001, "Search Agent": 0.02}


def row(path):
    r = json.loads((path / "revision.json").read_text())
    item = next(i for i in r["items"] if i.get("before"))
    plan = item.get("plan") or {}
    trace = r["trace"]
    cost = sum((t.get("cost_usd") or 0) if t["api"] == "Router" else COST.get(t["api"], 0) for t in trace)
    agent = item.get("agent") or {}
    steps = agent.get("steps", [])
    code = plan.get("code") or ""
    return {
        "run": path.name, "mode": item.get("mode", "pipeline"),
        "ok": r["preview_created"], "status": item["status"], "verdict": plan.get("verdict"),
        "seconds": r["seconds"],
        "router": sum(t["api"] == "Router" for t in trace),
        "search": sum(t["api"] == "Search" for t in trace),
        "search_agent": sum(t["api"] == "Search Agent" for t in trace),
        "run_example": sum(s["tool"] == "run_example" for s in steps),
        "rejected": sum(s["tool"] == "submit_revision" and not s.get("accepted") for s in steps),
        "models": sorted({t.get("model") for t in trace if t["api"] == "Router" and t.get("model")}),
        "cost_usd": round(cost, 3) if any(t.get("cost_usd") for t in trace if t["api"] == "Router") else None,
        "official_evidence": len(item.get("evidence") or []),
        "cited": len(plan.get("citations") or []),
        "create_agent": "create_agent(" in code,
    }


rows = [row(Path(p).parent) for p in sorted(glob.glob(sys.argv[1] + "/*/revision.json"))]
cols = list(rows[0])
print("| " + " | ".join(cols) + " |\n|" + "---|" * len(cols))
for x in rows:
    print("| " + " | ".join(str(x[c]) for c in cols) + " |")
