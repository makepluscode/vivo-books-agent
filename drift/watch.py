"""책 저장소 감시기 — 라이브러리 새 버전을 감지하면 Liner 에이전트로 책을 개정하고 PR을 열어요.

    python -m drift.watch --repo makepluscode/vivo-books-sample-book --once            # 1회 확인
    python -m drift.watch --repo makepluscode/vivo-books-sample-book --interval 600   # 10분마다 감시
    python -m drift.watch --repo ... --once --dry-run                           # PR 없이 브랜치·본문만 만들어 보기

흐름: 책 저장소 받기 → book.json `watch`의 PyPI 패키지 최신 버전 확인 → 책에 고정된 버전(pins)과 다르면
→ 영향 장 개정(`living.run`, Liner 에이전트) → 개정 원고·requirements.txt·정오표·개정 이력·개정 EPUB 커밋 → PR.

검증은 이 컴퓨터의 목표 환경(.target-env)에 설치된 버전으로 해요. PyPI 최신과 다르면 PR 본문에 둘 다 적어요.
GitHub 웹훅은 공개 주소가 필요해서, 지금은 폴링(주기적 확인)으로 감지해요.
"""
import argparse
import difflib
import json
import re
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

from . import living, probe

ROOT = Path(__file__).resolve().parent.parent
WATCH_OUT = ROOT / "out" / "watch"


def sh(*args, cwd=None, check=True):
    r = subprocess.run(list(args), cwd=cwd, capture_output=True, text=True, check=False)
    if check and r.returncode:
        raise RuntimeError(f"{' '.join(args[:3])} 실패: {r.stderr.strip()[-400:]}")
    return r.stdout.strip()


def checkout(repo, workdir):
    """책 저장소를 받아 기본 브랜치 최신 상태로 맞춰요."""
    if (workdir / ".git").exists():
        sh("git", "fetch", "-q", "origin", cwd=workdir)
        branch = sh("git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD", cwd=workdir).split("/", 1)[1]
        sh("git", "checkout", "-q", branch, cwd=workdir)
        sh("git", "reset", "-q", "--hard", f"origin/{branch}", cwd=workdir)
    else:
        workdir.parent.mkdir(parents=True, exist_ok=True)
        sh("gh", "repo", "clone", repo, str(workdir), "--", "-q")
        branch = sh("git", "symbolic-ref", "--short", "HEAD", cwd=workdir)
    return branch


def pypi_latest(package):
    r = requests.get(f"https://pypi.org/pypi/{package}/json", timeout=30)
    r.raise_for_status()
    info = r.json()
    version = info["info"]["version"]
    uploaded = min((u["upload_time"] for u in info.get("urls", [])), default=None)
    return version, uploaded


def detect(book, recorded_releases=None):
    """책에 고정된 버전과 PyPI 최신 버전이 다른 패키지를 찾아요."""
    pins = book.get("pins", {})
    changes = []
    for w in book.get("watch", []):
        pkg = w["pypi"]
        latest, uploaded = pypi_latest(pkg) if recorded_releases is None else recorded_releases[pkg]
        if pins.get(pkg) and Version(latest) > Version(pins[pkg]):
            changes.append({"package": pkg, "repository": w["repository"], "pinned": pins[pkg],
                            "latest": latest, "uploaded": uploaded})
    return changes


def event_for(changes, target):
    main = changes[0]
    return {"action": "published", "repository": {"full_name": main["repository"]},
            "release": {"tag_name": f"{main['package']}=={main['latest']}",
                        "body": "PyPI 폴링으로 감지한 새 버전이에요. 이 페이로드는 점검 계기일 뿐, API 변경의 근거가 아니에요."},
            "detected": changes, "verified_target": target,
            "delivery": "drift.watch PyPI polling; not a received GitHub webhook"}


def short(text, n=120):
    """한도를 넘으면 단어 경계에서 줄여요(한 단어가 너무 길면 글자 단위)."""
    text = " ".join(str(text or "").split())
    if len(text) <= n:
        return text
    cut = text[:n - 1]
    if " " in cut[n // 2:]:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:") + "…"


def cell(text):
    """마크다운 표 칸: 줄바꿈 없애고 `|` 이스케이프."""
    return str(text).replace("|", "\\|")


def change_rows(result):
    """PR 본문·개정 이력에 쓰는 장별 한 줄 요약."""
    rows = []
    for i in result["items"]:
        label = living.chapter_label(i["chapter_id"])
        if i["status"] == "unchanged":
            rows.append((label, "의존성 없음", "유지", "—", "—"))
            continue
        lookup = {e["id"]: e for e in i.get("evidence", [])}
        cites = [c for c in (i.get("plan") or {}).get("citations") or [] if isinstance(c, dict) and lookup.get(c.get("evidence_id"))]
        evidence = "<br>".join(f"[{short(lookup[c['evidence_id']]['title'], 40)}]({lookup[c['evidence_id']]['url']}) “{short(c['quote'], 70)}”"
                               for c in cites[:2]) or "—"
        if i.get("prose_changes"):
            applied = [c for c in i["prose_changes"] if c.get("applied")]
            synced = sum(c.get("basis") == "verified-target" for c in applied)
            cited = sum(c.get("basis") == "official-citation" for c in applied)
            pip_checks = [c["check"] for c in applied if c["kind"] == "pip"]
            install = "설치 가능 확인(pip dry-run)" if pip_checks else "—"
            rows.append((label, "고정 버전 표기·옛 API 설명", f"버전 표기 {synced}곳 동기화 · 본문 문장 {cited}곳",
                         evidence, install))
            continue
        before = short(str((i.get("before") or {}).get("error", "")).split(" (<target-env>")[0], 70)
        after = i.get("after") or {}
        verified = living.verification_text(after) if after.get("status") == "ok" else (i.get("status_reason_ko") or "보류")
        fix = "코드·설명 문단" if i["status"] == "verified-change" else "보류"
        rows.append((label, f"`{before}`" if before else "—", fix, evidence, verified))
    return rows


def agent_steps(result):
    steps = {living.chapter_label(i["chapter_id"]): (i.get("agent") or {}).get("steps", [])
             for i in result["items"] if i.get("agent")}
    for i in result["items"]:
        for c in i.get("prose_changes", []):
            if c.get("agent"):
                steps.setdefault(living.chapter_label(i["chapter_id"]) + " 본문", []).extend(c["agent"].get("steps", []))
    return steps


def pr_body(result, changes, target, steps_by_chapter):
    lines = ["## 📘 VIVO BOOKS가 책을 개정했어요", ""]
    for c in changes:
        lines.append(f"- **감지:** PyPI `{c['package']}` {c['pinned']} → **{c['latest']}** (업로드 {str(c['uploaded'])[:10]})")
    lines.append("- **검증 환경:** " + ", ".join(f"`{k}=={v}`" for k, v in target.items() if v)
                 + " (이 목표 환경에서 실제로 실행해 확인했어요)")
    if any(Version(target[c["package"]]) < Version(c["latest"]) for c in changes if target.get(c["package"])):
        lines.append("- 감지한 최신 버전과 검증 버전이 달라요. 설치된 버전까지 개정했고, 목표 환경을 올리면 다시 점검해요.")
    lines += ["", "## 바뀐 내용", "", "| 장 | 문제(관측) | 수정 | 근거 (Liner Search · 공식 문서) | 검증 |", "|---|---|---|---|---|"]
    lines += ["| " + " | ".join(cell(x) for x in r) + " |" for r in change_rows(result)]
    for item in result["items"]:
        after = item.get("after") or {}
        observed = after.get("tool_result_observation") or {}
        if after.get("status") == "ok" and observed.get("before") is not None:
            lines.extend(["", f"**{living.chapter_label(item['chapter_id'])} 도구 응답 변경 전후의 최종 답**",
                          f"- 변경 전 `{observed['before']}`", f"- 변경 후 `{observed['after']}`"])
    checks = ["- [ ] 바뀐 설명 문단과 본문 문장이 책의 문체·흐름에 맞는지 확인해 주세요."]
    if any("Final Answer:" in str((i.get("plan") or {}).get("code", "")) for i in result["items"]):
        checks.append("- [ ] 7장의 `Final Answer: ` 접두사 처리는 테스트 모델 전용이에요. 실제 LLM 예제 문맥에 맞는지 확인해 주세요.")
    unknown = {(i["chapter_id"], c.get("line")) for i in result["items"] for c in i.get("prose_changes", [])
               if c.get("verdict") == "UNKNOWN"}
    if unknown:
        checks.append(f"- [ ] 근거가 부족해 판단을 보류한 문장 {len(unknown)}곳은 원문을 유지했어요.")
    lines += ["", "## 저자 확인 필요", ""] + checks
    lines += ["", "## Liner 에이전트 조사 과정", ""]
    lines += ["RED는 원고에서 확인한 문제, YELLOW는 수정 권장, UNKNOWN은 판단 보류예요. 아래 ‘통과’는 제출안을 받았다는 표시예요.", ""]
    for chapter, steps in steps_by_chapter.items():
        lines.append(f"<details><summary>{chapter} · {len(steps)}단계</summary>\n")
        for n, s in enumerate(steps, 1):
            what = s.get("query") or s.get("question") or s.get("command") or s.get("verdict") or ""
            status = s.get("status") or ("통과" if s.get("accepted") else ("거절" if "accepted" in s else ""))
            err = f" · {short(s.get('error'), 80)}" if s.get("error") else ""
            lines.append(f"{n}. (턴 {s['turn']}) `{s['tool']}` {short(what, 100)} {status}{err}".rstrip())
        lines.append("\n</details>")
    lines += ["", "---", "에이전트는 제안만 해요. 공식 문서 인용 대조와 목표 환경 실행 검증을 통과한 수정만 이 PR에 들어 있어요.",
              "`dist/`의 개정 EPUB과 `REVISIONS.md`에 근거·검증 이력이 있어요. 병합 전까지는 저자 검토용 미리보기예요."]
    return "\n".join(lines)


def errata_section(result, revision, date):
    lines = [f"## {revision} · {date}", ""]
    for i in result["items"]:
        if i["status"] != "verified-change":
            continue
        label = living.chapter_label(i["chapter_id"])
        if i.get("prose_changes"):
            for c in i["prose_changes"]:
                if c.get("applied"):
                    lines += [f"- {label} {c['line']}행", f"  - 이전: {c['before']}", f"  - 이후: {c['after']}"]
        else:
            lines += [f"- {label} 예제: {sentences((i.get('plan') or {}).get('reason_ko'), 200)}", *code_errata(i)]
    return "\n".join(lines) + "\n"


def sentences(text, limit):
    """독자용 문장: 한도 안에서 문장 단위로 끊고, 첫 문장이 길면 단어 경계에서 줄여요."""
    text = " ".join(str(text or "").split())
    parts = re.findall(r".+?(?:[.!?](?=\s|$)|$)", text)
    kept = ""
    for part in (p.strip() for p in parts if p.strip()):
        if kept and len(kept) + 1 + len(part) > limit:
            break
        kept = f"{kept} {part}".strip()
    if len(kept) > limit:
        kept = kept[:limit].rsplit(" ", 1)[0] + "…"
    return kept


def code_errata(item):
    """정오표 하위 항목: 바뀐 코드 줄(적으면 그대로, 많으면 import만)과 설명 문단 변경 여부."""
    before = [line for line in (item.get("original_code") or "").splitlines() if line.strip()]
    after = [line for line in ((item.get("plan") or {}).get("code") or "").splitlines() if line.strip()]
    if not before or not after:
        return []
    diff = list(difflib.ndiff(before, after))
    removed = [d[2:].strip() for d in diff if d.startswith("- ")]
    added = [d[2:].strip() for d in diff if d.startswith("+ ")]
    out = []
    if len(removed) <= 2 and len(added) <= 2:
        out += [f"  - 이전: `{line}`" for line in removed] + [f"  - 이후: `{line}`" for line in added]
    else:
        def imports(rows):
            return [r for r in rows if r.startswith(("import ", "from "))]
        out.append(f"  - 예제 코드를 새 방식으로 다시 썼어요(삭제 {len(removed)}줄 · 추가 {len(added)}줄). "
                   "전체 코드는 개정판을 확인해 주세요.")
        out += [f"  - 이전 import: `{line}`" for line in imports(removed)]
        out += [f"  - 이후 import: `{line}`" for line in imports(added)]
    if any(str(loc).startswith("설명 문단") for loc in item.get("change_locations") or []):
        out.append("  - 예제를 설명하는 문단도 새 코드에 맞게 고쳤어요.")
    return out


def updated_requirements(text, pins, updates):
    """책에 선언된 단일 고정 버전만 바꿔요. 설정과 파일이 다르면 먼저 수정해야 해요."""
    pending = {canonicalize_name(p): (pins[p], v) for p, v in updates.items() if p in pins and pins[p] != v}
    seen = set()
    lines = []
    for line in text.splitlines(keepends=True):
        match = re.match(r"\s*([a-zA-Z0-9_.-]+)", line)
        pkg = canonicalize_name(match.group(1)) if match else None
        if pkg in pending:
            old, new = pending[pkg]
            spec = Requirement(line.partition("#")[0].strip())
            if str(spec.specifier) != f"=={old}" or spec.marker or spec.url or pkg in seen:
                raise ValueError(f"requirements.txt의 {pkg} 버전이 book.json 고정 버전과 맞지 않아요.")
            line = re.sub(r"(==\s*)" + re.escape(old) + r"(?![\w.+-])", lambda m: m[1] + new, line, count=1)
            seen.add(pkg)
        lines.append(line)
    if pending.keys() - seen:
        raise ValueError("requirements.txt에 개정할 패키지 고정 버전이 없어요: " + ", ".join(sorted(pending.keys() - seen)))
    return "".join(lines)


def apply_to_repo(workdir, book, result, out_dir, target, changes, revision):
    """개정 결과를 책 저장소 작업 트리에 써요."""
    req = workdir / "requirements.txt"
    requirements = updated_requirements(req.read_text(), book["pins"], target) if req.exists() else None
    for ch in book["chapters"]:
        src = living.local_path(out_dir / "chapters", ch["path"])
        shutil.copy(src, living.local_path(workdir, ch["path"]))
    if requirements is not None:
        req.write_text(requirements)
    items = {item["chapter_id"]: item for item in result["items"]}
    for ch in book["chapters"]:
        plan = items.get(ch["id"], {}).get("plan") or {}
        if ch.get("example") and items[ch["id"]]["status"] == "verified-change" and isinstance(plan.get("code"), str):
            living.local_path(workdir, ch["example"]).write_text(plan["code"].rstrip("\n") + "\n")
    data = json.loads((workdir / "book.json").read_text())
    data["pins"] = {k: target.get(k) or v for k, v in data.get("pins", {}).items()}
    data["revision"] = revision
    for chapter in data["chapters"]:
        edits = [c for c in items[chapter["id"]].get("prose_changes", []) if c.get("applied") and c.get("lines")]
        for field in ("version_lines", "required_prose_lines", "local_prose_lines"):
            if field in chapter:
                chapter[field] = sorted({revised_line(line, edits) for line in chapter[field]})
    (workdir / "book.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    dist = workdir / "dist"
    dist.mkdir(exist_ok=True)
    shutil.copy(out_dir / "preview.epub", dist / f"{book['book_id']}-{revision}-preview.epub")
    date = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    errata = workdir / "ERRATA.md"
    head = errata.read_text() if errata.exists() else "# 독자 정오표\n\n"
    errata.write_text(head.rstrip() + "\n\n" + errata_section(result, revision, date))
    rev = workdir / "REVISIONS.md"
    head = rev.read_text() if rev.exists() else "# 개정 이력\n\n"
    detected = ", ".join(f"{c['package']} {c['pinned']} → {c['latest']}" for c in changes)
    table = ["| 장 | 문제 | 수정 | 근거 | 검증 |", "|---|---|---|---|---|"] + ["| " + " | ".join(cell(x) for x in r) + " |" for r in change_rows(result)]
    rev.write_text(head.rstrip() + f"\n\n## {revision} 미리보기 · {date}\n\n감지: {detected} · 검증 환경: "
                   + ", ".join(f"{k}=={v}" for k, v in target.items() if v) + "\n\n" + "\n".join(table) + "\n")


def revised_line(line, edits):
    offset = 0
    for change in sorted(edits, key=lambda c: c["line"]):
        start, end = change["lines"]
        if line < start:
            break
        if line <= end:
            return start + offset
        offset += len(change["after"].splitlines()) - (end - start + 1)
    return line + offset


def cycle(repo, dry_run=False, force=False, cache=None, offline=False, *, recording=None):
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo) or any(part in {".", ".."} for part in repo.split("/")):
        raise ValueError("책 저장소를 owner/name 형식으로 입력해 주세요.")
    slug = repo.replace("/", "__")
    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    base = WATCH_OUT / slug if recording is None else WATCH_OUT / "demo" / run_id
    workdir = base / "repo"
    state_file = base / "state.json"
    state = json.loads(state_file.read_text()) if state_file.exists() else {}
    opened = state.setdefault("pull_requests", {})
    recorded_releases = None
    if recording is None:
        default = checkout(repo, workdir)
    else:
        dry_run = True
        recorded_releases = json.loads(Path(recording).read_text())["releases"]
        shutil.copytree(living.SAMPLE, workdir, ignore=shutil.ignore_patterns("__pycache__"))
        default = "main"
        sh("git", "init", "-q", "-b", default, cwd=workdir)
        sh("git", "add", ".", cwd=workdir)
        sh("git", "-c", "user.name=VIVO BOOKS", "-c", "user.email=noreply@vivolabs.org",
           "commit", "-qm", "r1 가상 기술서", cwd=workdir)
    book = json.loads((workdir / "book.json").read_text())
    changes = detect(book, recorded_releases)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not changes:
        print(f"[{now}] {repo}: 고정 버전이 PyPI 최신과 같아요. 변경 없음.")
        return None
    releases = {c["package"]: c["latest"] for c in changes}
    target = probe.target_versions(book.get("target_packages", living.DEFAULT_TARGET))
    scoped = living.watched_pins(book, target, {c["repository"] for c in changes})
    pending = [p for p in releases if not scoped.get(p) or Version(scoped[p]) <= Version(book["pins"][p])]
    if pending:
        print(f"[{now}] {repo}: 목표 환경을 먼저 갱신하거나 영향받는 장을 설정해 주세요 → " + ", ".join(pending))
        return None
    updates = {p: v for p, v in scoped.items() if p in book["pins"] and Version(v) > Version(book["pins"][p])}
    base_head = sh("git", "rev-parse", "HEAD", cwd=workdir)
    key = living.digest(json.dumps([base_head, releases, target], sort_keys=True))
    if not dry_run and not force and (previous := opened.get(key)):
        status = sh("gh", "pr", "view", previous, "--repo", repo, "--json", "state", "--jq", ".state", cwd=workdir)
        if status in {"OPEN", "MERGED"}:
            print(f"[{now}] {repo}: 이 원고와 검증 버전의 PR이 이미 있어요 → {previous}")
            return None
    print(f"[{now}] {repo}: 새 버전 감지 → " + ", ".join(f"{p}=={v}" for p, v in releases.items()))
    event = event_for(changes, target)
    out_dir = base / "runs" / run_id if recorded_releases is None else base / "artifacts"
    out_dir.mkdir(parents=True)
    if cache:
        shutil.copytree(cache, out_dir / "cache")
    event_path = out_dir / "event.json"
    event_path.write_text(json.dumps(event, ensure_ascii=False, indent=2))
    result = living.run(book_path=workdir / "book.json", event_path=event_path, out_dir=out_dir,
                        emit=lambda e: print(json.dumps({k: v for k, v in e.items() if k in {"type", "chapter_id", "tool", "query", "status", "verdict", "accepted", "api", "mode"}}, ensure_ascii=False)),
                        offline=offline, mode="agent", recording=recording)
    if not result["preview_created"]:
        print("개정 미리보기를 만들지 못했어요(보류 항목 있음). PR을 열지 않아요: " + living.hold_summary(result))
        return {"result": result, "pr": None}
    revision = result["preview_revision"]
    branch = f"drift/{changes[0]['package']}-{changes[0]['latest']}-{run_id}"
    sh("git", "checkout", "-q", "-b", branch, cwd=workdir)
    apply_to_repo(workdir, book, result, out_dir, updates, changes, revision)
    epub = f"dist/{book['book_id']}-{revision}-preview.epub"
    paths = [ch["path"] for ch in book["chapters"]] + [ch["example"] for ch in book["chapters"] if ch.get("example")]
    paths += ["book.json", "ERRATA.md", "REVISIONS.md"]
    if (workdir / "requirements.txt").exists():
        paths.append("requirements.txt")
    sh("git", "add", "--", *paths, cwd=workdir)
    sh("git", "add", "-f", "--", epub, cwd=workdir)
    title = f"📘 {revision} 개정 미리보기: " + ", ".join(f"{p} {v}" for p, v in updates.items())
    sh("git", "-c", "user.name=VIVO BOOKS", "-c", "user.email=noreply@vivolabs.org",
       "commit", "-q", "-m", title + "\n\nLiner Search·Router 근거와 목표 환경 실행 검증을 통과한 수정만 반영했어요.", cwd=workdir)
    body = pr_body(result, changes, target, agent_steps(result))
    (out_dir / "pr.md").write_text(body)
    if dry_run:
        print(f"[dry-run] 브랜치 {branch} 를 로컬에만 만들었어요. PR 본문: {out_dir / 'pr.md'}")
        print(f"  책 저장소: {workdir} · 정오표·개정 이력·EPUB은 이 브랜치에 있어요"
              f" (예: git -C {workdir} show {branch}:ERRATA.md)")
        sh("git", "checkout", "-q", default, cwd=workdir)
        return {"result": result, "pr": None, "branch": branch, "output": out_dir}
    sh("git", "push", "-q", "-u", "origin", branch, cwd=workdir)
    url = sh("gh", "pr", "create", "--repo", repo, "--base", default, "--head", branch,
             "--title", title, "--body-file", str(out_dir / "pr.md"), cwd=workdir)
    opened[key] = url
    temp_state = state_file.with_suffix(".tmp")
    living.json_write(temp_state, state)
    temp_state.replace(state_file)
    sh("git", "checkout", "-q", default, cwd=workdir)
    print(f"PR: {url}")
    return {"result": result, "pr": url, "branch": branch}


def main():
    ap = argparse.ArgumentParser(description="책 저장소 감시 → Liner 에이전트 개정 → PR")
    source = ap.add_mutually_exclusive_group(required=True)
    source.add_argument("--repo", help="owner/name")
    source.add_argument("--replay-demo", action="store_true", help="동봉된 감시 기록으로 로컬 PR 초안을 만들어요")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=int, default=600, help="감시 주기(초)")
    ap.add_argument("--dry-run", action="store_true", help="push·PR 없이 로컬 브랜치와 PR 본문만 만들어요")
    ap.add_argument("--force", action="store_true", help="이미 처리한 버전도 다시 처리해요")
    ap.add_argument("--cache", type=Path, help="이전 실행의 Liner 캐시 폴더(재생·비용 절감)")
    ap.add_argument("--offline", action="store_true", help="캐시만 사용하고 신규 Liner 호출을 거부해요")
    a = ap.parse_args()
    if a.replay_demo:
        outcome = cycle("demo/book", recording=living.DEMO_RECORDING)
        if not outcome or not outcome["result"]["preview_created"]:
            raise SystemExit(2)
        return
    while True:
        try:
            cycle(a.repo, a.dry_run, a.force, a.cache, a.offline)
        except Exception as exc:  # 감시는 계속해요
            print(f"오류: {type(exc).__name__}: {exc}")
            if a.once:
                raise
        if a.once:
            break
        time.sleep(a.interval)


if __name__ == "__main__":
    main()
