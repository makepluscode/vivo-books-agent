"""목표 환경 실행 확인(정적 + import 수준).

모델 판정과 별개로, 목표 환경(.target-env)에 원고·수정안이 쓰는 심볼이 실제로 있는지 확인해요.
코드를 '실행'하지는 않아요(API 키·하드웨어가 필요한 호출 제외). 모듈 import 와 속성 존재·폐기 표시만 봐요.
"""
import ast
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

TARGET_PY = Path(__file__).resolve().parent.parent / ".target-env" / "bin" / "python"

_PROBE_SRC = r'''
import importlib, json, sys, warnings
def _is_field(cls, name):
    for k in ("model_fields", "__fields__", "__dataclass_fields__"):
        try:
            if name in (getattr(cls, k, None) or {}):
                return True
        except Exception:
            pass
    return any(name in getattr(c, "__annotations__", {}) for c in getattr(cls, "__mro__", ()))
out = {}
for spec in json.loads(sys.argv[1]):
    mod, _, attr = spec.partition(":")
    r = {"exists": False, "deprecated": False, "error": None, "warnings": []}
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        try:
            obj = importlib.import_module(mod)
            parts = [p for p in attr.split(".") if p]
            for i, part in enumerate(parts):
                if not hasattr(obj, part) and isinstance(obj, type) and _is_field(obj, part):
                    # 클래스 속성이 아니라 인스턴스 필드(pydantic·dataclass·어노테이션)인 경우
                    r["instance_field"] = True
                    break
                obj = getattr(obj, part)
                # 제거된 API 자리에 남겨 둔 안내용 대리 객체(예: openai.ChatCompletion)는 '없음'으로 봐요.
                if "removed" in type(obj).__name__.lower():
                    raise AttributeError(f"{part}: 제거된 API의 안내용 대리 객체({type(obj).__name__})")
            r["exists"] = True
            doc = (getattr(obj, "__doc__", "") or "").lower()
            head = doc.strip().split("\n\n")[0][:400]  # 첫 문단만(본문 어딘가의 'deprecated' 언급은 제외)
            r["deprecated"] = (bool(getattr(obj, "__deprecated__", None)) or ".. deprecated::" in doc
                               or "deprecated" in head)
        except Exception as e:
            r["error"] = f"{type(e).__name__}: {e}"[:200]
        r["warnings"] = sorted({f"{x.category.__name__}: {str(x.message)[:160]}" for x in w
                               if issubclass(x.category, (DeprecationWarning, FutureWarning))
                               and (attr.split(".")[-1] or mod.split(".")[-1]) in str(x.message)})[:3]
    if r["warnings"]:
        r["deprecated"] = True
    out[spec] = r
print(json.dumps(out))
'''


def symbols_from_code(code):
    """import 와 '모듈별칭.속성...' 체인을 뽑아요. 파싱 실패 시 빈 목록."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    alias, specs = {}, []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                alias[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
                specs.append(f"{a.name}:")
        elif isinstance(node, ast.ImportFrom) and node.module:
            for a in node.names:
                specs.append(f"{node.module}:{a.name}")
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            chain, cur = [], node
            while isinstance(cur, ast.Attribute):
                chain.append(cur.attr)
                cur = cur.value
            if isinstance(cur, ast.Name) and cur.id in alias:
                chain.reverse()
                # 모듈 경로 vs 속성 경계는 런타임에서 판단하기 어려워 '모듈:속성체인' 하나로 둬요.
                specs.append(f"{alias[cur.id]}:{'.'.join(chain)}")
    # 상위 체인만 남기기(a.b 와 a.b.c 가 모두 있으면 둘 다 유지 — 어디서 끊기는지 보이도록)
    return sorted(set(specs))


# ---------- 격리 실행 공통 ----------
MEM_LIMIT = 6 * 1024 ** 3      # 가상 메모리 6GB(torch import 여유)
FSIZE_LIMIT = 16 * 1024 ** 2   # 쓰기 파일 16MB
OUT_LIMIT = 64 * 1024          # 읽어 올 출력 64KB


def sandbox_available():
    return bool(shutil.which("bwrap")) and bool(shutil.which("prlimit")) and TARGET_PY.exists()


TMP_LIMIT = 64 * 1024 ** 2      # 격리 /tmp 전체 64MB
NPROC_EXTRA = 128               # 실행 중 새로 만들 수 있는 프로세스·스레드 수(사용자 기존 수 + 64)


def _nproc_cap():
    try:
        uid = str(os.getuid())
        n = 0
        for d in Path("/proc").iterdir():
            if not d.name.isdigit():
                continue
            try:
                st = (d / "status").read_text()
            except OSError:
                continue
            if f"Uid:\t{uid}\t" in st:  # RLIMIT_NPROC 는 스레드까지 세요
                threads = next((line.split()[1] for line in st.splitlines() if line.startswith("Threads:")), "1")
                n += int(threads)
    except Exception:
        n = 512
    return n + NPROC_EXTRA


def _sandboxed(args, timeout):
    """bwrap 허용 목록 격리: /usr(읽기 전용)·목표 환경(읽기 전용)·빈 /tmp(64MB) 만 보여요.
    홈·/etc·프로젝트(.env 포함)·네트워크·호스트 PID·환경변수는 보이지 않아요.
    자원 제한은 prlimit 로(메모리·파일 크기·프로세스 수) 걸어요 — 스레드 안전하지 않은 preexec_fn 은 쓰지 않아요."""
    import tempfile
    venv = str(TARGET_PY.parent.parent)
    cmd = ["prlimit", f"--as={MEM_LIMIT}", f"--fsize={FSIZE_LIMIT}", "--core=0", f"--nproc={_nproc_cap()}", "--",
           "bwrap", "--ro-bind", "/usr", "/usr", "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64",
           "--symlink", "usr/bin", "/bin", "--dev", "/dev", "--proc", "/proc", "--size", str(TMP_LIMIT), "--tmpfs", "/tmp",
           "--ro-bind", venv, venv, "--chdir", "/tmp", "--unshare-all", "--die-with-parent", "--new-session",
           "--clearenv", "--setenv", "PATH", "/usr/bin", "--setenv", "HOME", "/tmp", "--setenv", "OMP_NUM_THREADS", "2",
           "--setenv", "MPLBACKEND", "Agg", str(TARGET_PY), "-I", "-W", "default"] + args
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        try:
            p = subprocess.run(cmd, stdout=out, stderr=err, timeout=timeout, check=False)
            rc, timed_out = p.returncode, False
        except subprocess.TimeoutExpired:
            rc, timed_out = None, True
        res = []
        for f in (out, err):
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - OUT_LIMIT))
            res.append(f.read().decode("utf-8", "replace"))
    return rc, timed_out, res[0], res[1]


def probe(specs):
    specs = sorted({s for s in specs if s and ":" in s})
    if not specs:
        return {}
    if not sandbox_available():
        return {s: {"exists": None, "error": "격리 환경(bwrap/.target-env) 없음 — 확인 생략"} for s in specs}
    rc, to, out, err = _sandboxed(["-c", _PROBE_SRC, json.dumps(specs)], 180)
    if rc != 0:
        return {s: {"exists": None, "error": ("시간 초과" if to else _scrub(err[-300:]))} for s in specs}
    res = json.loads(out.strip().splitlines()[-1])
    for r in res.values():
        if r.get("error"):
            r["error"] = _scrub(r["error"])
    return res


def target_versions(pkgs):
    if not TARGET_PY.exists():
        return {}
    src = ("import json,sys,importlib.metadata as m\nout={}\nfor p in json.loads(sys.argv[1]):\n"
           "  try: out[p]=m.version(p)\n  except Exception: out[p]=None\nprint(json.dumps(out))")
    p = subprocess.run([str(TARGET_PY), "-I", "-c", src, json.dumps(pkgs)], capture_output=True, text=True, check=False)
    return json.loads(p.stdout) if p.returncode == 0 else {}


# ---------- pip 설치 가능 여부 ----------
_SPEC = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(\[[A-Za-z0-9,._-]+\])?((==|>=|<=|~=|!=|>|<)[A-Za-z0-9.*+!_-]+)?$")


def pip_specs(command):
    """단순 패키지 설치 명령만 확인해요. 옵션·URL·경로가 있으면 보류해요."""
    try:
        tokens = shlex.split(command.replace("\\\n", " "), comments=True)
    except ValueError:
        return []
    if tokens[:2] in (["pip", "install"], ["pip3", "install"]):
        specs = tokens[2:]
    elif tokens[:4] in (["python", "-m", "pip", "install"], ["python3", "-m", "pip", "install"]):
        specs = tokens[4:]
    else:
        return []
    return specs if len(specs) <= 12 and all(_SPEC.fullmatch(t) for t in specs) else []


def pip_check(command, timeout=120):
    """목표 Python에서 패키지 조합을 wheel만 사용해 설치 모의 실행해요."""
    specs = pip_specs(command)
    if not specs:
        return {}
    try:
        p = subprocess.run([str(TARGET_PY), "-m", "pip", "install", "--dry-run", "--only-binary=:all:", "-q",
                            "--disable-pip-version-check", *specs],
                           capture_output=True, text=True, timeout=timeout, check=False)
        ok = p.returncode == 0
        errors = p.stderr.strip().splitlines()
        detail = "" if ok else next((line for line in errors if "ERROR" in line), errors[-1] if errors else "")
    except (OSError, subprocess.TimeoutExpired) as exc:
        ok = None
        detail = "설치 검사 시간 초과" if isinstance(exc, subprocess.TimeoutExpired) else "목표 Python 실행 불가"
    return {spec: {"installable": ok, "detail": _scrub(detail)[:200]} for spec in specs}


def pip_result(pip):
    if any(v["installable"] is False for v in pip.values()):
        return {"status": "fail", "detail": "패키지 조합 설치 불가: " + ", ".join(pip)}
    if not pip or any(v["installable"] is not True for v in pip.values()):
        return {"status": "skipped", "detail": "설치 가능 여부를 확인하지 못했어요."}
    return {"status": "ok", "detail": "모든 패키지 설치 가능(dry-run)"}


# ---------- 실행 확인 ----------
# 외부 API 단계에서 멈췄다고 볼 수 있는 '마지막 예외' 클래스(접두 일치). 그 외는 fail.
_API_STOP = ("openai.OpenAIError", "openai.APIConnectionError", "openai.AuthenticationError",
             "httpx.ConnectError", "requests.exceptions.ConnectionError", "urllib3.exceptions.",
             "anthropic.APIConnectionError", "langchain_openai", "socket.gaierror",
             # 데이터셋 다운로드 등 표준 라이브러리의 네트워크 접근(격리 환경은 네트워크 차단)
             "urllib.error.URLError")


def run_snippet(code, timeout=60):
    """목표 환경(격리)에서 코드 조각을 실제 실행해 결과를 분류해요.

    ok          : 끝까지 실행됨
    needs_api   : 외부 API 연결/인증 예외로 멈춤 — 그 앞 단계(import·객체 구성)까지만 실행 확인, 호출 자체는 미검증
    context     : 조각 안에서 정의·import 되지 않은 이름 때문에 멈춤(원고 앞부분 정의 추정)
    timeout     : 시간 초과(원인 미상)
    fail        : 그 밖의 예외(API 불일치 등)
    skipped     : 격리 환경 없음
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return {"status": "fail", "detail": f"구문 오류: {e.msg}"}
    if not sandbox_available():
        return {"status": "skipped", "detail": "격리 환경(bwrap/.target-env)이 없어 실행하지 않았어요"}
    rc, timed_out, _out, err = _sandboxed(["-c", code], timeout)
    if timed_out:
        return {"status": "timeout", "detail": f"{timeout}s 시간 초과"}
    lines = err.strip().splitlines()
    last = lines[-1] if lines else ""
    warns = [line.strip() for line in lines if "Warning:" in line and line.startswith("<string>")][:2]
    if rc == 0:
        return {"status": "ok", "detail": "", "warnings": [_scrub(w) for w in warns]}
    exc = next((line for line in reversed(lines)
                if line and not line.startswith(" ") and ":" in line and "Error" in line.split(":")[0]), last)
    if exc.startswith(_API_STOP) or any(f"{m}" in exc.split(":")[0] for m in ("APIConnectionError", "AuthenticationError")):
        status = "needs_api"
    elif exc.startswith("NameError"):
        defined = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
        name = exc.split("'")[1] if exc.count("'") >= 2 else ""
        status = "context" if name and name not in defined else "fail"
    else:
        status = "fail"
    return {"status": status, "detail": _scrub(exc)[:240], "warnings": [_scrub(w) for w in warns]}


def _scrub(text):
    """보고서·화면에 로컬 절대 경로가 드러나지 않게 줄여요."""
    import re
    text = text.replace(str(TARGET_PY.parent.parent), "<target-env>")
    return re.sub(r"/home/[^\s'\"]+?/site-packages", "<site-packages>", text)


if __name__ == "__main__":
    print(json.dumps(probe(sys.argv[1:]), ensure_ascii=False, indent=2))
