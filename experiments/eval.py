"""파이프라인 결과(result.json)를 정답지와 비교해요.

사용: .venv/bin/python experiments/eval.py out/run1/result.json samples/chapter03.expected.json
매칭: 줄 범위가 겹치는 예측 항목. 한 정답에 여러 예측이 겹치면 가장 심각한 판정을 대표로 써요.
"""
import json
import sys
from collections import Counter

SEV = {"RED": 3, "YELLOW": 2, "UNKNOWN": 1, "GREEN": 0}


def overlap(a, b):
    return not (a[1] < b[0] or b[1] < a[0])


def main(res_path, exp_path):
    res = json.load(open(res_path))
    exp = json.load(open(exp_path))
    preds = res["items"]
    rows, used, conf = [], set(), Counter()
    for x in exp["items"]:
        m = [i for i, p in enumerate(preds) if overlap(p["item"]["lines"], x["lines"])]
        # 같은 줄의 문장 항목이 여러 개면(7줄) 종류·주제로 더 좁혀요.
        if x["kind"] == "sentence" and len(m) > 1:
            key = "humble" if "ros" in x["id"] else ("4o" if "model" in x["id"] else "")
            narrowed = [i for i in m if key and key in json.dumps(preds[i], ensure_ascii=False).lower()]
            m = narrowed or m
        used.update(m)
        got = max((preds[i]["verdict"]["verdict"] for i in m), key=lambda v: SEV[v], default="MISSING")
        ok = got == x["expected"] or got in x.get("accept", [])
        rows.append({"id": x["id"], "expected": x["expected"], "got": got, "ok": ok, "bonus": x.get("bonus", False)})
        if not x.get("bonus"):
            conf[(x["expected"], got)] += 1
    scored = [r for r in rows if not r["bonus"]]
    extra = [p["item"]["id"] for i, p in enumerate(preds) if i not in used]
    cites = [c for p in preds for c in p["verdict"].get("citations", [])]
    valid = [c for c in cites if c.get("valid")]
    summary = {
        "accuracy": f"{sum(r['ok'] for r in scored)}/{len(scored)}",
        "detected": f"{sum(r['got'] != 'MISSING' for r in scored)}/{len(scored)}",
        "false_alarm_on_green": [r["id"] for r in scored if r["expected"] == "GREEN" and r["got"] in ("RED", "YELLOW")],
        "fabricated_on_unknown": [r["id"] for r in scored if r["expected"] == "UNKNOWN" and r["got"] in ("RED", "YELLOW", "GREEN")],
        "bonus_hit": [r["id"] for r in rows if r["bonus"] and r["ok"]],
        "extra_items": extra,
        "citations_valid": f"{len(valid)}/{len(cites)}",
        "quotes_found": f"{sum(1 for c in valid if c.get('quote_found'))}/{len(valid)}",
        "escalated": sum(1 for p in preds if len(p.get("steps", [])) > 1),
        "errors": [p["item"]["id"] for p in preds if p.get("error")],
        "seconds_total": res["seconds_total"],
        "seconds_extract": res["seconds_extract"],
        "item_seconds_max": max((p.get("seconds") or 0) for p in preds) if preds else 0,
        "served_models": dict(Counter(t.get("served_model") for t in res["trace"] if t.get("served_model"))),
    }
    for r in rows:
        print(f"{'✅' if r['ok'] else '❌'} {r['id']:<24} 기대 {r['expected']:<8} 결과 {r['got']}{' (보너스)' if r['bonus'] else ''}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    main(*sys.argv[1:3])
