import ast
import json
import pathlib
import subprocess
import sys

repo, py = pathlib.Path(sys.argv[1]), sys.argv[2]
LC = ("langchain", "langgraph")
files = {}
for f in sorted(repo.rglob("*.py")):
    if ".git" in f.parts:
        continue
    try:
        tree = ast.parse(f.read_text(encoding="utf-8"))
    except Exception as e:
        files[str(f.relative_to(repo))] = [("PARSE", str(e))]
        continue
    stmts = []
    for n in ast.walk(tree):
        if (
            isinstance(n, ast.ImportFrom)
            and n.module
            and n.module.split(".")[0].startswith(LC)
            and n.level == 0
        ):
            stmts.append(
                f"from {n.module} import " + ", ".join(a.name for a in n.names)
            )
        elif isinstance(n, ast.Import):
            for a in n.names:
                if a.name.split(".")[0].startswith(LC):
                    stmts.append(f"import {a.name}")
    files[str(f.relative_to(repo))] = stmts
cache = {}


def ok(s):
    if s not in cache:
        r = subprocess.run(
            [py, "-W", "ignore", "-c", s], capture_output=True, text=True, timeout=120, check=False
        )
        cache[s] = (r.returncode == 0, (r.stderr.strip().splitlines() or [""])[-1])
    return cache[s]


out = {}
for f, stmts in files.items():
    out[f] = [(s, *ok(s)) for s in stmts]
with open(sys.argv[3], "w", encoding="utf-8") as result_file:
    json.dump(out, result_file, ensure_ascii=False, indent=1)
lc_files = {f: r for f, r in out.items() if r}
broken = {
    f: [x for x in r if not x[1]]
    for f, r in lc_files.items()
    if any(not x[1] for x in r)
}
print(
    "py files:", len(out), "| using langchain:", len(lc_files), "| broken:", len(broken)
)
for f, xs in broken.items():
    for s, _, err in xs:
        print(f"  {f}: {s}\n      -> {err}")
