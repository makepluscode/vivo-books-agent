"""결과 → 정오표(Markdown) · 원고 diff · HTML 보고서 · 원자료(JSON)."""
import difflib
import html
import json
from pathlib import Path

ICON = {"RED": "🔴", "YELLOW": "🟡", "GREEN": "🟢", "UNKNOWN": "⚪"}
LABEL = {"RED": "실행 불가", "YELLOW": "권장 변경", "GREEN": "최신", "UNKNOWN": "판단 보류"}
ORDER = {"RED": 0, "YELLOW": 1, "UNKNOWN": 2, "GREEN": 3}


RUN_ICON = {"ok": "✅", "needs_api": "🔑", "context": "🧩", "fail": "❌", "timeout": "⏱️", "skipped": "⏭️"}
RUN_TXT = {"ok": "끝까지 실행", "needs_api": "외부 API 연결 직전까지 실행 (호출 자체는 미검증)",
           "context": "앞 절에서 정의되는 이름 필요", "fail": "실패", "timeout": "시간 초과", "skipped": "생략"}


def _safe_url(u):
    u = str(u or "")
    return u if u.startswith(("https://", "http://")) else "#"


def _sorted(items):
    return sorted(items, key=lambda r: (ORDER.get(r["verdict"]["verdict"], 9), r["item"]["lines"][0]))


def apply_fixes(md, items):
    """겹치지 않는 수정안만 아래쪽부터 적용해요. 원고 파일은 덮어쓰지 않아요."""
    lines = md.splitlines()
    fixes = [r for r in items if r["verdict"].get("fix")]
    fixes.sort(key=lambda r: r["item"]["lines"][0], reverse=True)
    taken, applied = set(), []
    for r in fixes:
        s, e = r["item"]["lines"]
        span = set(range(s, e + 1))
        if r.get("fix_run") and r["fix_run"]["status"] != "ok":
            r["held"] = "수정안 실행을 확인하지 못해 적용을 보류했어요."
            continue
        if span & taken:
            r["held"] = "다른 수정안과 줄이 겹쳐 적용 보류"
            continue
        taken |= span
        lines[s - 1:e] = r["verdict"]["fix"].rstrip("\n").splitlines()
        applied.append(r["item"]["id"])
    return "\n".join(lines) + "\n", applied


def errata_md(result, source_name):
    out = [f"# 정오표 — {source_name}", "", f"점검 기준(목표 환경): {result['target']}", "",
           "| 위치 | 상태 | 내용 | 근거 |", "|---|---|---|---|"]
    for r in _sorted(result["items"]):
        v = r["verdict"]
        if v["verdict"] == "GREEN" or v.get("merged_into"):
            continue
        s, e = r["item"]["lines"]
        cites = [c for c in v.get("citations", []) if c.get("valid")]
        links = " ".join(f"[{i}]({_safe_url(c['url'])})" for i, c in enumerate(cites, 1)) or "—"
        out.append(f"| {s}–{e}줄 | {ICON[v['verdict']]} {LABEL[v['verdict']]} | "
                   f"{r['item'].get('subject', '')}: {v.get('reason', '').replace('|', '/')} | {links} |")
    out += ["", ("> 수정안은 Liner 검색 근거와 목표 환경의 심볼 확인을 바탕으로 만든 **검토용 제안**이에요. "
                 "실제 실행 검증 전에는 저자·편집자가 확인해 주세요.")]
    return "\n".join(out) + "\n"


def _h(s):
    return html.escape(str(s or ""))


def html_report(result, md, source_name, diff_text, applied):
    counts = dict.fromkeys(ORDER, 0)
    for r in result["items"]:
        counts[r["verdict"]["verdict"]] += 1
    trace = result["trace"]
    n_search = sum(1 for t in trace if t["api"] == "search")
    n_agent = sum(1 for t in trace if t["api"] == "search_agent")
    n_router = sum(1 for t in trace if t["api"] in ("extract", "judge", "merge"))
    models = sorted({t.get("served_model") for t in trace if t.get("served_model")})
    cards = []
    for r in _sorted(result["items"]):
        v, it = r["verdict"], r["item"]
        s, e = it["lines"]
        orig = "\n".join(md.splitlines()[s - 1:e])
        cites = "".join(
            f"<li><a href='{_h(_safe_url(c['url']))}' target='_blank' rel='noopener'>{_h(c.get('title') or c['url'])}</a>"
            f" <span class='src'>{'Search Agent' if c.get('source') == 'search_agent' else 'Search'}</span>"
            f"{'' if c.get('quote_found') else ' <span class=warn>인용 불일치</span>'}"
            f"<blockquote>{_h(c.get('quote'))}</blockquote></li>"
            for c in v.get("citations", []) if c.get("valid"))
        probes = "".join(
            f"<li><code>{_h(k)}</code> — {'✅ 있음' if p.get('exists') else ('❔ 확인 불가' if p.get('exists') is None else '❌ 없음')}"
            f"{' · ⚠️ 폐기 표시' if p.get('deprecated') else ''}</li>"
            for k, p in (r.get("probe") or {}).items())
        fixp = r.get("fix_probe") or {}
        fix_ok = (all(p.get("exists") for p in fixp.values()) if fixp else None)
        fix_badge = ("" if fix_ok is None else
                     ("<span class='ok'>수정안 심볼 모두 목표 환경에 있음</span>" if fix_ok
                      else "<span class='warn'>수정안 일부 심볼이 목표 환경에 없음</span>"))
        run_html = ""
        if r.get("run") or r.get("fix_run"):
            run_html = ("<h4>목표 환경 실제 실행</h4><ul>"
                        + (f"<li>원고: {RUN_ICON.get(r['run']['status'], '')} {_h(RUN_TXT.get(r['run']['status']))}"
                           f" <code>{_h(r['run'].get('detail'))}</code>"
                           + "".join(f"<br><small>⚠️ {_h(w)}</small>" for w in r['run'].get('warnings') or []) + "</li>"
                           if r.get("run") else "")
                        + (f"<li>수정안: {RUN_ICON.get(r['fix_run']['status'], '')} {_h(RUN_TXT.get(r['fix_run']['status']))}"
                           f" <code>{_h(r['fix_run'].get('detail'))}</code></li>" if r.get("fix_run") else "")
                        + "</ul>")
        steps = " → ".join(f"{_h(x['stage'])}: {_h(x['verdict'])}" for x in r.get("steps", []))
        held = f" <span class='warn'>{_h(r['held'])}</span>" if r.get("held") else ""
        fix_html = (f"<h4>수정 제안 {fix_badge}{held}</h4><pre class='fix'>{_h(v['fix'])}</pre>"
                    + (f"<p class='note'>{_h(v.get('fix_note'))}</p>" if v.get("fix_note") else "")
                    if v.get("fix") else "")
        cards.append(f"""
<section class="card {v['verdict'].lower()}">
  <header><span class="badge">{ICON[v['verdict']]} {LABEL[v['verdict']]}</span>
    <b>{_h(it.get('subject'))}</b><span class="loc">{s}–{e}줄 · {_h(it.get('kind'))} · {r.get('seconds', '-')}s</span></header>
  <p>{_h(v.get('reason'))}</p>
  <details {'open' if v['verdict'] in ('RED', 'YELLOW') else ''}><summary>원고 · 근거 · 확인 결과</summary>
    <h4>원고</h4><pre>{_h(orig)}</pre>
    {fix_html}
    <h4>Liner 근거</h4><ol>{cites or '<li>인용된 근거 없음</li>'}</ol>
    {run_html}
    <h4>목표 환경 심볼 확인</h4><ul>{probes or '<li>확인 대상 없음</li>'}</ul>
    <p class="note">처리 단계: {steps} · 검색어: <code>{_h(it.get('query'))}</code></p>
  </details>
</section>""")
    trace_rows = "".join(
        f"<tr><td>{_h(t['api'])}</td><td>{_h(t.get('item') or '-')}</td>"
        f"<td>{_h(t.get('served_model') or t.get('query') or t.get('question', '')[:60])}</td><td>{t['seconds']}s</td></tr>"
        for t in trace)
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>기술서 갱신 점검</title>
<style>
:root{{--bg:#fafaf8;--fg:#1d1d1b;--muted:#6b6b66;--card:#fff;--line:#e4e2dc;--red:#d64545;--yellow:#c99a06;--green:#2f9e5b;--gray:#8a8a85;--code:#f3f2ee}}
@media (prefers-color-scheme:dark){{:root{{--bg:#161615;--fg:#ecebe6;--muted:#a3a29c;--card:#1f1f1d;--line:#34332f;--code:#262624}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.6 -apple-system,"Pretendard","Noto Sans KR",sans-serif}}
main{{max-width:960px;margin:0 auto;padding:24px 16px}}
h1{{font-size:22px;margin:0 0 4px}} .sub{{color:var(--muted);margin:0 0 20px}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;margin-bottom:20px}}
.stat{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px}}
.stat b{{display:block;font-size:22px}} .stat span{{color:var(--muted);font-size:13px}}
.card{{background:var(--card);border:1px solid var(--line);border-left:5px solid var(--gray);border-radius:10px;padding:12px 16px;margin:12px 0}}
.card.red{{border-left-color:var(--red)}} .card.yellow{{border-left-color:var(--yellow)}} .card.green{{border-left-color:var(--green)}}
.card header{{display:flex;flex-wrap:wrap;gap:8px;align-items:baseline}} .loc{{color:var(--muted);font-size:13px;margin-left:auto}}
.badge{{font-weight:600}} pre{{background:var(--code);padding:10px;border-radius:8px;overflow:auto;font-size:13px}}
pre.fix{{border:1px dashed var(--green)}} blockquote{{margin:4px 0 8px;color:var(--muted);font-size:13px;border-left:3px solid var(--line);padding-left:8px}}
.src{{font-size:12px;border:1px solid var(--line);border-radius:6px;padding:0 6px;color:var(--muted)}}
.warn{{color:var(--red);font-size:12px}} .ok{{color:var(--green);font-size:12px}} .note{{color:var(--muted);font-size:13px}}
table{{width:100%;border-collapse:collapse;font-size:13px}} td{{border-bottom:1px solid var(--line);padding:4px 6px;word-break:break-all}}
h2{{font-size:17px;margin-top:28px}} h4{{margin:12px 0 4px;font-size:14px}}
</style></head><body><main>
<h1>기술서 갱신 점검 — {_h(source_name)}</h1>
<p class="sub">목표 환경: {_h(result['target'])}</p>
<div class="stats">
<div class="stat"><b>🔴 {counts['RED']}</b><span>실행 불가</span></div>
<div class="stat"><b>🟡 {counts['YELLOW']}</b><span>권장 변경</span></div>
<div class="stat"><b>⚪ {counts['UNKNOWN']}</b><span>판단 보류</span></div>
<div class="stat"><b>🟢 {counts['GREEN']}</b><span>최신</span></div>
<div class="stat"><b>{result['seconds_total']}s</b><span>장 전체 처리</span></div>
</div>
{''.join(cards)}
<h2>원고 수정안(diff) — 적용 {len(applied)}건</h2><pre>{_h(diff_text) or '변경 없음'}</pre>
<h2>Liner API 처리 과정</h2>
<p class="note">Search {n_search}회 · Router {n_router}회(응답 모델: {_h(', '.join(models))}) · Search Agent {n_agent}회</p>
<table><tr><td><b>API</b></td><td><b>항목</b></td><td><b>모델/검색어</b></td><td><b>시간</b></td></tr>{trace_rows}</table>
</main></body></html>"""


def write_all(result, md, source_path, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    name = Path(source_path).name
    fixed, applied = apply_fixes(md, result["items"])
    diff_text = "".join(difflib.unified_diff(md.splitlines(True), fixed.splitlines(True),
                                             f"a/{name}", f"b/{name}"))
    (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    (out / "errata.md").write_text(errata_md(result, name))
    (out / "manuscript.diff").write_text(diff_text)
    (out / "report.html").write_text(html_report(result, md, name, diff_text, applied))
    return out
