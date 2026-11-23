"""데모용 로컬 웹앱 — 점검 과정을 실시간으로 보여줘요.

사용: .venv/bin/python -m drift.web [--port 8765]  →  http://127.0.0.1:8765
- '실시간 점검': Liner API를 실제 호출해요(장 1회 약 $0.3).
- '기록 재생': 이전 실시간 점검의 이벤트 기록(events.jsonl)을 그대로 다시 보여줘요(API 호출 없음, 데모 안전장치).
로컬 전용(127.0.0.1)이에요. 외부에 노출하지 마세요.
"""
import argparse
import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import liner, living, pipeline, report
from .__main__ import default_target

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
OUT = ROOT / "out" / "web"
LIVING_OUT = ROOT / "out" / "living"
DEMO_SNAPSHOT = ROOT / "demo" / "snapshot"
PACKAGED_ONLY = False  # --packaged: 로컬 실행 결과 대신 동봉한 심사 자료만 보여줘요
JOBS = {}
RUN_LOCK = threading.Lock()  # 실시간 점검은 한 번에 하나(추적 기록이 전역이라)


class Job:
    def __init__(self, name, mode):
        self.id = time.strftime("%H%M%S-") + uuid.uuid4().hex[:4]
        self.name, self.mode = name, mode
        self.events, self.cond = [], threading.Condition()
        self.done = False
        self.t0 = time.time()

    def push(self, ev):
        ev = {**ev, "t": round(time.time() - self.t0, 2)}
        with self.cond:
            self.events.append(ev)
            self.cond.notify_all()

    def finish(self):
        with self.cond:
            self.done = True
            self.cond.notify_all()


def _live(job):
    """RUN_LOCK 은 호출 전에 이미 잡혀 있어요(접수 시점에 비차단 획득). 끝나면 반드시 풀고 finish 해요."""
    out_dir = OUT / job.id
    md = ""
    try:
        md = (SAMPLES / f"{job.name}.md").read_text()
        liner.TRACE.clear()
        pipeline.EMIT = job.push
        liner.ON_LOG = lambda e: job.push({"type": "api", **{k: e.get(k) for k in
                                           ("api", "item", "query", "served_model", "seconds", "n", "question")}})
        target = default_target()
        mode = getattr(job, "revise_mode", "pipeline")
        job.push({"type": "start", "target": target, "mode": "live · " + ("Liner 에이전트" if mode == "agent" else "고정 경로")})
        result = pipeline.run(md, target, mode=mode)
        report.write_all(result, md, SAMPLES / f"{job.name}.md", out_dir)
        job.push({"type": "done", "seconds": result["seconds_total"], "report": f"/out/{job.id}/report.html",
                  "errata": f"/out/{job.id}/errata.md", "diff": f"/out/{job.id}/manuscript.diff"})
    except Exception as exc:
        job.push({"type": "error", "message": f"{type(exc).__name__}: {exc}"[:300]})
    finally:
        pipeline.EMIT = None
        liner.ON_LOG = None
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "events.jsonl").write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in job.events))
            (out_dir / "source.txt").write_text(job.name)
            (out_dir / "source.md").write_text(md)  # 재생 때 당시 원고 그대로 보여주려고 스냅샷 저장
        except Exception as exc:
            job.push({"type": "error", "message": f"기록 저장 실패: {exc}"[:300]})
        RUN_LOCK.release()
        job.finish()


def _replay(job, src_id, speed):
    try:
        _replay_inner(job, src_id, speed)
    except Exception as exc:
        job.push({"type": "error", "message": f"재생 실패: {type(exc).__name__}: {exc}"[:300]})
    finally:
        job.finish()


def _replay_inner(job, src_id, speed):
    src = OUT / src_id
    events = [json.loads(line) for line in (src / "events.jsonl").read_text().splitlines() if line.strip()]
    last = 0.0
    for ev in events:
        time.sleep(max(0.0, (ev.get("t", last) - last) / speed))
        last = ev.get("t", last)
        ev = dict(ev)
        if ev["type"] == "start":
            ev["mode"] = f"replay ×{speed:g} (기록: {src_id})"
        if ev["type"] == "done":  # 재생은 기록 폴더의 결과물만 가리키게 다시 만들어요(기록 내용 불신)
            ev.update({"report": f"/out/{src_id}/report.html", "errata": f"/out/{src_id}/errata.md",
                       "diff": f"/out/{src_id}/manuscript.diff"})
        job.push(ev)


def recordings():
    out = []
    if OUT.exists():
        for d in sorted(OUT.iterdir(), reverse=True):
            if all((d / f).exists() for f in ("events.jsonl", "report.html", "source.md")):
                out.append({"id": d.name, "sample": (d / "source.txt").read_text() if (d / "source.txt").exists() else "?"})
    return out


def _living(job):
    try:
        output = LIVING_OUT / job.id
        result = living.run(out_dir=output, emit=job.push, mode=job.revise_mode)
        job.push({"type": "living_done", "result": result,
                  "reader": f"/living-out/{job.id}/reader.html",
                  "epub": f"/living-out/{job.id}/preview.epub" if result["preview_created"] else None,
                  "diff": f"/living-out/{job.id}/manuscript.diff"})
    except Exception as exc:
        job.push({"type": "error", "message": f"{type(exc).__name__}: {exc}"[:300]})
    finally:
        RUN_LOCK.release()
        job.finish()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        b = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path == "/":
            return self._send(200, (Path(__file__).parent / "web.html").read_text(), "text/html; charset=utf-8")
        if u.path == "/living":
            return self._send(200, (Path(__file__).parent / "living_web.html").read_text(), "text/html; charset=utf-8")
        if u.path == "/api/living/snapshot":
            candidates = [] if PACKAGED_ONLY else list(LIVING_OUT.glob("*/revision.json"))
            if candidates:
                f = max(candidates, key=lambda p: p.stat().st_mtime)
                prefix = f"/living-out/{f.parent.name}"
            else:
                f = DEMO_SNAPSHOT / "revision.json"
                prefix = "/living-out/packaged"
            if not f.is_file():
                return self._send(404, "{}")
            result = json.loads(f.read_text())
            return self._send(200, json.dumps({"result": result, "recorded": True,
                "reader": f"{prefix}/reader.html",
                "epub": f"{prefix}/preview.epub" if result["preview_created"] else None,
                "diff": f"{prefix}/manuscript.diff"}, ensure_ascii=False))
        if u.path.startswith("/living-out/"):
            parts = u.path.split("/")
            allowed = {"reader.html", "original.epub", "preview.epub", "manuscript.diff", "revision.json", "original.md", "revised.md", "events.jsonl"}
            if len(parts) == 4 and parts[3] in allowed:
                packaged = parts[2] == "packaged"
                directory = DEMO_SNAPSHOT if packaged else LIVING_OUT / parts[2]
                f = directory / parts[3]
                if ((packaged or directory.resolve().parent == LIVING_OUT.resolve())
                        and f.resolve().parent == directory.resolve() and f.is_file()):
                    ctype = {".html": "text/html; charset=utf-8", ".epub": "application/epub+zip", ".json": "application/json; charset=utf-8"}.get(f.suffix, "text/plain; charset=utf-8")
                    return self._send(200, f.read_bytes(), ctype)
            return self._send(404, "not found", "text/plain")
        if u.path == "/api/samples":
            names = sorted(p.stem for p in SAMPLES.glob("*.md"))
            return self._send(200, json.dumps({"samples": names, "recordings": recordings()}, ensure_ascii=False))
        if u.path == "/api/sample":
            name = q.get("name", "")
            if name not in {p.stem for p in SAMPLES.glob("*.md")}:
                return self._send(404, "{}")
            return self._send(200, json.dumps({"md": (SAMPLES / f"{name}.md").read_text()}, ensure_ascii=False))
        if u.path == "/api/events":
            return self._sse(q.get("job", ""))
        if u.path.startswith("/out/"):
            parts = u.path.split("/")
            if len(parts) == 4 and parts[3] in ("report.html", "errata.md", "manuscript.diff"):
                f = OUT / parts[2] / parts[3]
                if f.resolve().parent.parent == OUT.resolve() and f.exists():
                    ctype = "text/html; charset=utf-8" if f.suffix == ".html" else "text/plain; charset=utf-8"
                    return self._send(200, f.read_bytes(), ctype)
            return self._send(404, "not found", "text/plain")
        self._send(404, "not found", "text/plain")

    def do_POST(self):
        u = urlparse(self.path)
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if not 0 <= n <= 65536:
                return self._send(413, "{}")
            body = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(body, dict):
                return self._send(400, "{}")
        except (ValueError, UnicodeDecodeError):
            return self._send(400, "{}")
        if u.path == "/api/living/run":
            if not RUN_LOCK.acquire(blocking=False):
                return self._send(409, json.dumps({"error": "다른 점검이 진행 중이에요"}, ensure_ascii=False))
            job = Job("sample-book", "live")
            job.revise_mode = "agent" if body.get("mode") == "agent" else "pipeline"
            JOBS[job.id] = job
            threading.Thread(target=_living, args=(job,), daemon=True).start()
            return self._send(200, json.dumps({"job": job.id}))
        if u.path == "/api/run":
            name = body.get("name", "")
            if name not in {p.stem for p in SAMPLES.glob("*.md")}:
                return self._send(400, json.dumps({"error": "없는 샘플"}))
            if not RUN_LOCK.acquire(blocking=False):
                return self._send(409, json.dumps({"error": "다른 실시간 점검이 진행 중이에요"}, ensure_ascii=False))
            job = Job(name, "live")
            job.revise_mode = "agent" if body.get("mode") == "agent" else "pipeline"
            JOBS[job.id] = job
            threading.Thread(target=_live, args=(job,), daemon=True).start()
            return self._send(200, json.dumps({"job": job.id}))
        if u.path == "/api/replay":
            rec = body.get("id", "")
            if rec not in {r["id"] for r in recordings()}:
                return self._send(400, json.dumps({"error": "없는 기록"}))
            src_name = (OUT / rec / "source.txt").read_text()
            md = (OUT / rec / "source.md").read_text()
            try:
                speed = min(20.0, max(1.0, float(body.get("speed", 4))))
            except (TypeError, ValueError):
                speed = 4.0
            job = Job(src_name, "replay")
            JOBS[job.id] = job
            threading.Thread(target=_replay, args=(job, rec, speed), daemon=True).start()
            return self._send(200, json.dumps({"job": job.id, "sample": src_name, "md": md}, ensure_ascii=False))
        self._send(404, "{}")

    def _sse(self, job_id):
        job = JOBS.get(job_id)
        if not job:
            return self._send(404, "{}")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:  # 브라우저 자동 재연결 시 Last-Event-ID 다음부터 보내 중복 집계를 막아요
            i = int(self.headers.get("Last-Event-ID", "-1")) + 1
        except ValueError:
            i = 0
        try:
            while True:
                with job.cond:
                    while i >= len(job.events) and not job.done:
                        job.cond.wait(15)
                        if i >= len(job.events) and not job.done:
                            self.wfile.write(b": ping\n\n")
                            self.wfile.flush()
                    batch, finished = job.events[i:], job.done
                for k, ev in enumerate(batch, i):
                    self.wfile.write(f"id: {k}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n".encode())
                i += len(batch)
                self.wfile.flush()
                if finished and i >= len(job.events):
                    self.wfile.write(b"event: end\ndata: {}\n\n")
                    self.wfile.flush()
                    return
        except (BrokenPipeError, ConnectionResetError):
            return


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--packaged", action="store_true", help="기록 결과로 demo/snapshot의 동봉 자료만 보여줘요")
    a = ap.parse_args()
    global PACKAGED_ONLY
    PACKAGED_ONLY = a.packaged
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    print(f"http://127.0.0.1:{a.port}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
