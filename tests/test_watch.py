"""책 저장소 감시기(drift/watch.py) — 네트워크·GitHub 없이 감지·PR 본문·저장소 반영을 검증해요."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from drift import probe, watch

BOOK = {"book_id": "demo", "revision": "r1", "pins": {"langchain": "0.3.25", "langchain-core": "0.3.61"},
        "watch": [{"pypi": "langchain", "repository": "langchain-ai/langchain"},
                  {"pypi": "langchain-core", "repository": "langchain-ai/langchain"}],
        "chapters": [{"id": "chapter01", "path": "chapters/chapter01.md"}, {"id": "chapter07", "path": "chapters/chapter07.md"}]}
EV = {"id": "s1", "title": "Guide | docs", "url": "https://docs.langchain.com/oss/python/migrate/langchain-v1", "description": "x"}
RESULT = {"items": [
    {"chapter_id": "chapter01", "status": "verified-change", "evidence": [EV],
     "plan": {"citations": [{"evidence_id": "s1", "quote": "create_agent is the standard way"}]},
     "prose_changes": [{"line": 10, "kind": "pip", "basis": "verified-target", "applied": True, "check": {"langchain==1.5.0": True},
                        "before": "pip install langchain==0.3.25", "after": "pip install langchain==1.5.0"}]},
    {"chapter_id": "chapter07", "status": "verified-change", "evidence": [EV], "before": {"status": "fail", "error": "ImportError: Tool"},
     "after": {"status": "ok", "agent_flow_verified": True}, "agent": {"steps": [{"turn": 1, "tool": "liner_search", "query": "q"}]},
     "plan": {"code": "x", "reason_ko": "Tool 제거", "citations": [{"evidence_id": "s1", "quote": "create_agent is the standard way"}]}}]}


class WatchTests(unittest.TestCase):
    def test_detect_reports_only_packages_newer_than_pins(self):
        latest = {"langchain": ("1.5.2", "2026-11-18"), "langchain-core": ("0.3.61", "2025-05-01")}
        with patch.object(watch, "pypi_latest", side_effect=lambda p: latest[p]):
            changes = watch.detect(BOOK)
        self.assertEqual([(c["package"], c["pinned"], c["latest"]) for c in changes], [("langchain", "0.3.25", "1.5.2")])

    def test_detect_ignores_older_index_versions(self):
        with patch.object(watch, "pypi_latest", return_value=("0.1.0", None)):
            self.assertEqual(watch.detect(BOOK), [])

    def test_requirements_updates_a_declared_pin_only(self):
        text = "other-langchain==0.3.25\nlangchain==0.3.25 # pinned\n"
        self.assertEqual(watch.updated_requirements(text, BOOK["pins"], {"langchain": "1.5.0"}),
                         "other-langchain==0.3.25\nlangchain==1.5.0 # pinned\n")
        with self.assertRaisesRegex(ValueError, "버전이 book.json"):
            watch.updated_requirements("langchain==0.3.25.post1\n", BOOK["pins"], {"langchain": "1.5.0"})

    def test_prose_anchor_moves_with_multiline_revision(self):
        edits = [{"line": 13, "lines": [13, 13], "after": "first\nsecond"}]
        self.assertEqual([watch.revised_line(line, edits) for line in (5, 13, 15)], [5, 13, 16])

    def test_install_check_resolves_the_whole_group(self):
        with patch.object(probe.subprocess, "run", return_value=watch.subprocess.CompletedProcess([], 1, "", "ERROR conflict")) as run:
            result = probe.pip_check("pip install fastapi==0.95.0 pydantic==2.0.0")
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0][-2:], ["fastapi==0.95.0", "pydantic==2.0.0"])
        self.assertNotIn("--no-deps", run.call_args.args[0])
        self.assertEqual(probe.pip_result(result)["status"], "fail")
        self.assertEqual(probe.pip_result({"p": {"installable": None}})["status"], "skipped")

    def test_pr_body_has_table_evidence_and_escaped_pipes(self):
        body = watch.pr_body(RESULT, [{"package": "langchain", "pinned": "0.3.25", "latest": "1.5.2", "uploaded": "2026-11-18"}],
                             {"langchain": "1.5.0"}, watch.agent_steps(RESULT))
        self.assertIn("0.3.25 → **1.5.2**", body)
        self.assertIn("`langchain==1.5.0`", body)
        self.assertIn("Guide \\| docs", body)
        self.assertIn("설치 가능 확인(pip dry-run)", body)
        self.assertIn("Seoul·Busan·Jeju", body)
        self.assertIn("(턴 1) `liner_search`", body)

    def test_apply_to_repo_updates_pins_errata_and_dist(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, out = Path(tmp) / "repo", Path(tmp) / "out"
            for base in (repo, out / "chapters"):
                (base / "chapters").mkdir(parents=True)
            (repo / "book.json").write_text(json.dumps(BOOK))
            (repo / "requirements.txt").write_text("langchain==0.3.25\nlangchain-core==0.3.61\npandas==2.0\n")
            for ch in BOOK["chapters"]:
                (repo / ch["path"]).write_text("old")
                (out / "chapters" / ch["path"]).write_text("new " + ch["id"])
            (out / "preview.epub").write_bytes(b"epub")
            watch.apply_to_repo(repo, BOOK, RESULT, out, {"langchain": "1.5.0", "langchain-core": "1.8.1"},
                                [{"package": "langchain", "pinned": "0.3.25", "latest": "1.5.2"}], "r2")
            self.assertEqual((repo / "chapters/chapter07.md").read_text(), "new chapter07")
            self.assertEqual((repo / "requirements.txt").read_text(), "langchain==1.5.0\nlangchain-core==1.8.1\npandas==2.0\n")
            book = json.loads((repo / "book.json").read_text())
            self.assertEqual((book["revision"], book["pins"]["langchain"]), ("r2", "1.5.0"))
            self.assertTrue((repo / "dist/demo-r2-preview.epub").exists())
            errata = (repo / "ERRATA.md").read_text()
            self.assertIn("이후: pip install langchain==1.5.0", errata)
            self.assertIn("7장 예제: Tool 제거", errata)
            self.assertIn("r2 미리보기", (repo / "REVISIONS.md").read_text())

    def test_apply_to_repo_updates_the_chapter_example_file(self):
        book = {**BOOK, "chapters": [{"id": "chapter01", "path": "chapters/chapter01.md"},
                                     {"id": "chapter07", "path": "chapters/chapter07.md", "example": "ch07.py"}]}
        with tempfile.TemporaryDirectory() as tmp:
            repo, out = Path(tmp) / "repo", Path(tmp) / "out"
            for base in (repo, out / "chapters"):
                (base / "chapters").mkdir(parents=True)
            (repo / "book.json").write_text(json.dumps(book))
            (repo / "ch07.py").write_text("old code\n")
            for ch in book["chapters"]:
                (repo / ch["path"]).write_text("old")
                (out / "chapters" / ch["path"]).write_text("new")
            (out / "preview.epub").write_bytes(b"epub")
            watch.apply_to_repo(repo, book, RESULT, out, {"langchain": "1.5.0"},
                                [{"package": "langchain", "pinned": "0.3.25", "latest": "1.5.2"}], "r2")
            self.assertEqual((repo / "ch07.py").read_text(), "x\n")


    def test_errata_shows_changed_code_lines_in_whole_sentences(self):
        small = {"chapter_id": "chapter04", "status": "verified-change",
                 "original_code": "from langchain.prompts import ChatPromptTemplate\nprint(1)\n",
                 "change_locations": ["설명 문단 1곳 (원본 6행부터)", "Python 코드 블록 1곳 (원본 10행부터)"],
                 "plan": {"code": "from langchain_core.prompts import ChatPromptTemplate\nprint(1)\n",
                          "reason_ko": "모듈이 없어서 오류가 나요. " + "근거 문장이에요. " * 30}}
        rewrite = {"chapter_id": "chapter07", "status": "verified-change", "change_locations": [],
                   "original_code": "from a import Old\nx = 1\ny = 2\nz = 3\n",
                   "plan": {"code": "from b import New\nanswer = 42\n", "reason_ko": "Old가 없어요."}}
        errata = watch.errata_section({"items": [small, rewrite]}, "r2", "2026-11-22")
        self.assertNotIn("…", errata)
        self.assertIn("- 4장 예제: 모듈이 없어서 오류가 나요.", errata)
        self.assertIn("  - 이전: `from langchain.prompts import ChatPromptTemplate`", errata)
        self.assertIn("  - 이후: `from langchain_core.prompts import ChatPromptTemplate`", errata)
        self.assertIn("설명하는 문단도", errata.split("- 7장")[0])
        self.assertIn("다시 썼어요(삭제 4줄 · 추가 2줄)", errata)
        self.assertIn("  - 이전 import: `from a import Old`", errata)
        self.assertIn("  - 이후 import: `from b import New`", errata)
        self.assertNotIn("설명하는 문단도", errata.split("- 7장")[1])

    def test_short_cuts_at_word_boundary(self):
        self.assertEqual(watch.short("deprecated in favor of create_agent from the langchain package", 40),
                         "deprecated in favor of create_agent…")
        self.assertEqual(watch.short("abc", 40), "abc")


if __name__ == "__main__":
    unittest.main()
