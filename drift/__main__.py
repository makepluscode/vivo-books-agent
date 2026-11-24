"""사용: python -m drift <원고.md> [--out out/이름] [--agent] [--no-escalate] [--target "설명"]"""
import argparse
import json
from pathlib import Path

from . import pipeline, probe, report

DEFAULT_PKGS = ["langchain", "langchain-core", "langchain-openai", "langchain-classic", "openai", "pandas", "torch",
                "numpy", "scikit-learn", "pydantic", "matplotlib", "requests", "scipy", "Pillow", "networkx"]


def default_target():
    v = probe.target_versions(DEFAULT_PKGS)
    pk = ", ".join(f"{k}=={x}" for k, x in v.items() if x) or "PyPI 최신 안정 버전"
    return f"점검일 기준 최신 안정 버전 ({pk}; ROS 2는 최신 LTS 기준)"


def main():
    ap = argparse.ArgumentParser(prog="drift", description="기술서 갱신 점검 에이전트")
    ap.add_argument("source")
    ap.add_argument("--out", default=None)
    ap.add_argument("--target", default=None)
    ap.add_argument("--no-escalate", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--agent", action="store_true", help="항목마다 Liner 에이전트가 조사·판정해요 (drift/agent.py)")
    a = ap.parse_args()
    md = Path(a.source).read_text()
    target = a.target or default_target()
    print(f"목표 환경: {target}")
    result = pipeline.run(md, target, escalate=not a.no_escalate, workers=a.workers, mode="agent" if a.agent else "pipeline")
    out = report.write_all(result, md, a.source, a.out or f"out/{Path(a.source).stem}")
    for r in result["items"]:
        v = r["verdict"]
        print(f"{report.ICON[v['verdict']]} {r['item']['lines']} {r['item']['id']}: {(v.get('reason') or '')[:80]}"
              + (f"  [오류: {r['error']}]" if r.get("error") else ""))
    print(f"\n{result['seconds_total']}s · 결과: {out}/report.html")
    print(json.dumps({"api_calls": len(result['trace'])}))


if __name__ == "__main__":
    main()
