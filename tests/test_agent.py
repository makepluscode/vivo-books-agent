"""Drift Agent(drift/agent.py) 단위 테스트 — Liner 호출 없이 가짜 Router 응답으로 루프·게이트를 검증해요."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_living import DESCRIPTION, EVIDENCE, GOOD_CODE, PLAN, two_chapter_book

from drift import agent, living, report

RULES = [("docs.langchain.com", "/"), ("github.com", "/langchain-ai/langchain")]


def call(name, args, cid="c1"):
    return {"role": "assistant", "content": "", "tool_calls": [
        {"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}


class ScriptedGateway:
    """Router 턴을 순서대로 돌려주고, 받은 대화를 기록해요."""
    script = []
    search_rows = [EVIDENCE]

    def __init__(self, output, emit):
        self.trace, self.seen = [], []
        self.script = list(type(self).script)

    def search(self, query):
        self.trace.append({"api": "Search", "mode": "test", "query": query})
        return [dict(r) for r in type(self).search_rows]

    def agent(self, question):
        self.trace.append({"api": "Search Agent", "mode": "test"})
        return "context", [dict(EVIDENCE)]

    def chat(self, messages, tools):
        self.seen.append([dict(m) for m in messages])
        self.trace.append({"api": "Router", "mode": "test", "model": "test-model"})
        return self.script.pop(0) if self.script else {"role": "assistant", "content": "done"}


class DriftAgentTests(unittest.TestCase):
    def run_agent(self, script, verifier, search_rows=None):
        ScriptedGateway.script = script
        ScriptedGateway.search_rows = search_rows or [EVIDENCE]
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(living, "Gateway", ScriptedGateway), \
                patch.object(living, "verify", side_effect=verifier), \
                patch.object(agent, "official_rules", return_value=RULES), \
                patch.object(living.probe, "target_versions", return_value={"langchain": "test", "langchain-core": "test"}):
            result = living.run(book_path=two_chapter_book(tmp), out_dir=Path(tmp), mode="agent")
            revised = (Path(tmp) / "revised.md").read_text()
        return result, result["items"][1], revised

    @unittest.skipUnless(agent.probe.sandbox_available(), "isolated target unavailable")
    def test_search_then_verified_submit_changes_manuscript(self):
        script = [call("liner_search", {"query": "create_agent migration", "site": "docs.langchain.com"}),
                  call("run_example", {"code": GOOD_CODE}),
                  call("submit_revision", PLAN)]
        verdicts = iter([{"status": "fail", "error": "ImportError"}, {"status": "ok"}, {"status": "ok"}])
        result, item, revised = self.run_agent(script, lambda *a: next(verdicts))
        self.assertEqual(item["status"], "verified-change")
        self.assertTrue(result["preview_created"])
        self.assertIn(GOOD_CODE, revised)
        self.assertEqual([s["tool"] for s in item["agent"]["steps"]], ["liner_search", "run_example", "submit_revision"])
        self.assertEqual(item["agent"]["steps"][0]["query"], "site:docs.langchain.com create_agent migration")
        self.assertEqual(item["evidence"][0]["url"], EVIDENCE["url"])
        self.assertIn("Liner 에이전트가 고른 조사 순서", agent.trace_html(result))

    @unittest.skipUnless(agent.probe.sandbox_available(), "isolated target unavailable")
    def test_unofficial_citation_is_rejected_and_manuscript_kept(self):
        blog = {"title": "Blog", "url": "https://blog.example.com/langchain", "description": DESCRIPTION}
        plan = {**PLAN, "citations": [{"evidence_id": "s1", "quote": DESCRIPTION}]}
        script = [call("liner_search", {"query": "q"}), call("submit_revision", plan)]
        result, item, revised = self.run_agent(script, lambda *a: {"status": "fail", "error": "ImportError"}, [blog])
        self.assertEqual(item["status"], "blocked-evidence")
        self.assertFalse(result["preview_created"])
        self.assertEqual(item["evidence"], [])
        self.assertFalse(item["agent"]["steps"][-1]["accepted"])
        self.assertNotIn(GOOD_CODE, revised)

    @unittest.skipUnless(agent.probe.sandbox_available(), "isolated target unavailable")
    def test_failed_candidate_is_rejected_then_repaired(self):
        script = [call("liner_search", {"query": "q"}), call("submit_revision", PLAN), call("submit_revision", PLAN)]
        verdicts = iter([{"status": "fail", "error": "ImportError"},
                         {"status": "fail", "error": "bad candidate"}, {"status": "ok"}])
        _, item, _ = self.run_agent(script, lambda *a: next(verdicts))
        self.assertEqual(item["status"], "verified-change")
        self.assertTrue(item["self_repair"])
        self.assertIn("bad candidate", item["agent"]["steps"][1]["reasons"][0])

    @unittest.skipUnless(agent.probe.sandbox_available(), "isolated target unavailable")
    def test_first_accepted_submission_wins_within_one_router_turn(self):
        final = call("submit_revision", PLAN)
        final["tool_calls"] += call("submit_revision", {**PLAN, "code": "invalid"}, "later")["tool_calls"]
        results = iter([{"status": "fail", "error": "ImportError"}, {"status": "ok"}])
        _, item, revised = self.run_agent([call("liner_search", {"query": "q"}), final], lambda *a: next(results))
        self.assertEqual(item["plan"], PLAN)
        self.assertEqual(item["agent"]["tool_usage"]["submit_revision"], 1)
        self.assertIn(GOOD_CODE, revised)

    @unittest.skipUnless(agent.probe.sandbox_available(), "isolated target unavailable")
    def test_unknown_enum_value_is_rejected(self):
        _, item, _ = self.run_agent([call("liner_search", {"query": "q"}),
                                    call("submit_revision", {**PLAN, "verdict": "BLUE"})],
                                   lambda *a: {"status": "fail", "error": "ImportError"})
        self.assertFalse(item["agent"]["steps"][-1]["accepted"])
        self.assertEqual(item["agent"]["stop"], "budget")

    @unittest.skipUnless(agent.probe.sandbox_available(), "isolated target unavailable")
    def test_red_verdict_on_working_original_is_rejected(self):
        script = [call("liner_search", {"query": "q"}), call("submit_revision", PLAN)]
        _, item, _ = self.run_agent(script, lambda *a: {"status": "ok"})
        self.assertNotEqual(item["status"], "verified-change")
        self.assertIn("contradicts", item["agent"]["steps"][-1]["reasons"][0])

    @unittest.skipUnless(agent.probe.sandbox_available(), "isolated target unavailable")
    def test_search_budget_is_enforced(self):
        script = [call("liner_search", {"query": f"q{i}"}, f"c{i}") for i in range(6)]
        result, item, _ = self.run_agent(script, lambda *a: {"status": "fail", "error": "ImportError"})
        self.assertEqual(sum(t["api"] == "Search" for t in result["trace"]), agent.LIMITS["liner_search"])
        self.assertEqual(item["agent"]["stop"], "budget")
        self.assertTrue(item["status"].startswith("blocked"))

    @unittest.skipUnless(agent.probe.sandbox_available(), "isolated target unavailable")
    def test_no_tool_call_is_nudged_once_then_held(self):
        script = [{"role": "assistant", "content": "I think it is fine."}, {"role": "assistant", "content": "still fine"}]
        _, item, _ = self.run_agent(script, lambda *a: {"status": "fail", "error": "ImportError"})
        self.assertEqual(item["agent"]["turns"], 2)
        self.assertEqual(item["status"], "blocked-evidence")

    def test_official_rules_match_host_and_repository_prefix(self):
        self.assertTrue(agent.is_official("https://docs.langchain.com/oss/python/migrate", RULES))
        self.assertTrue(agent.is_official("https://github.com/langchain-ai/langchain/releases", RULES))
        for url in ["https://github.com/someone/langchain", "https://docs.langchain.com.evil.test/x",
                    "https://user@docs.langchain.com/x", "javascript:alert(1)", "https://github.com/langchain-ai/langchainx",
                    "https://docs.langchain.com/oss/javascript/langchain/agents"]:
            self.assertFalse(agent.is_official(url, RULES), url)

    def test_official_rules_from_target_metadata(self):
        if not agent.probe.TARGET_PY.exists():
            self.skipTest("목표 환경 없음")
        rules = agent.official_rules(["langchain"])
        self.assertIn(("docs.langchain.com", "/"), rules)
        self.assertIn(("github.com", "/langchain-ai/langchain"), rules)
        self.assertFalse(any(host in {"x.com", "www.reddit.com"} for host, _ in rules))


if __name__ == "__main__":
    unittest.main()


OFFICIAL_ROW = {"title": "pandas 2.0 whatsnew", "url": "https://pandas.pydata.org/docs/whatsnew/v2.0.0.html",
                "description": "DataFrame.append has been removed; use pandas.concat instead."}
BLOG_ROW = {"title": "blog", "url": "https://blog.example.com/pandas", "description": "DataFrame.append has been removed; use pandas.concat instead."}
MD = ["# 장", "```python", "df = df.append(row)", "```"]
ITEM = {"id": "pandas-append", "lines": [3, 3], "kind": "code", "subject": "append", "packages": ["pandas"], "symbols": []}


class InspectItemTests(unittest.TestCase):
    def inspect(self, script, rows, runs, item=ITEM, rules=(("pandas.pydata.org", "/"),)):
        script = list(script)
        runs = iter(runs)
        with patch.object(agent.liner, "router_chat_ex", side_effect=lambda *a, **k: (script.pop(0), "test-model")), \
                patch.object(agent.liner, "search", side_effect=lambda *a, **k: [dict(r) for r in rows]), \
                patch.object(agent.probe, "probe", return_value={}), \
                patch.object(agent.probe, "symbols_from_code", return_value=[]), \
                patch.object(agent, "official_rules", return_value=list(rules)), \
                patch("drift.pipeline.run_with_context", side_effect=lambda *a, **k: next(runs)):
            return agent.inspect_item(dict(item), MD, "pandas 3")

    def submit(self, verdict, quote, fix=None, cid="c9"):
        return call("submit_verdict", {"verdict": verdict, "reason": "r", "fix": fix,
                                       "citations": [{"evidence_id": "s1", "quote": quote}]}, cid)

    def test_red_with_official_quote_and_working_fix(self):
        rec = self.inspect([call("liner_search", {"query": "append removed", "site": "pandas.pydata.org"}),
                            self.submit("RED", "DataFrame.append has been removed", "df = pd.concat([df, row])")],
                           [OFFICIAL_ROW], [{"status": "fail", "detail": "AttributeError"}, {"status": "ok", "detail": ""}])
        v = rec["verdict"]
        self.assertEqual(v["verdict"], "RED")
        self.assertEqual(v["fix"], "df = pd.concat([df, row])")
        self.assertEqual(rec["fix_run"]["status"], "ok")
        self.assertEqual(v["citations"][0]["evidence"], 1)
        self.assertTrue(v["citations"][0]["quote_found"])
        self.assertEqual(rec["evidence"][0]["source"], "search:official")
        html = report.html_report({"target": "pandas 3", "items": [rec], "seconds_total": 1.0,
                                   "trace": [{"api": "extract", "seconds": 0.2},
                                             {"api": "agent-inspect", "seconds": 0.4},
                                             {"api": "agent-inspect", "seconds": 0.4}]},
                                  "\n".join(MD), "chapter03.md", "", [])
        self.assertIn("Router 3회", html)

    def test_unofficial_only_evidence_is_held_as_unknown(self):
        rec = self.inspect([call("liner_search", {"query": "q"})] + [self.submit("YELLOW", "DataFrame.append has been removed", cid=f"c{i}") for i in range(3)],
                           [BLOG_ROW], [{"status": "ok", "detail": ""}])
        self.assertEqual(rec["verdict"]["verdict"], "UNKNOWN")
        self.assertEqual(rec["verdict"]["held_from"], "YELLOW")
        self.assertEqual(rec["agent"]["stop"], "budget")

    def test_extractor_cannot_promote_an_unregistered_site(self):
        item = {**ITEM, "official_site": "blog.example.com"}
        rec = self.inspect([call("liner_search", {"query": "q"})] + [self.submit("YELLOW", BLOG_ROW["description"], cid=f"c{i}") for i in range(3)],
                           [BLOG_ROW], [{"status": "ok"}], item=item, rules=[])
        self.assertEqual(rec["official_sources"]["source"], "none")
        self.assertEqual(rec["verdict"]["verdict"], "UNKNOWN")

    def test_failing_fix_keeps_verdict_but_drops_fix(self):
        rec = self.inspect([call("liner_search", {"query": "q"})] + [self.submit("RED", "DataFrame.append has been removed", "bad()", f"c{i}") for i in range(3)],
                           [OFFICIAL_ROW], [{"status": "fail", "detail": "AttributeError"}] + [{"status": "fail", "detail": "NameError"}] * 3)
        self.assertEqual(rec["verdict"]["verdict"], "RED")
        self.assertIsNone(rec["verdict"]["fix"])
        self.assertEqual(rec["verdict"]["fix_original"], "bad()")

    def test_internal_sdk_without_official_source_can_be_unknown(self):
        item = {**ITEM, "id": "acme", "packages": ["acme-sdk"], "official_site": None}
        rec = self.inspect([call("submit_verdict", {"verdict": "UNKNOWN", "reason": "비공개 SDK", "citations": []})],
                           [], [{"status": "fail", "detail": "ModuleNotFoundError"}], item=item, rules=())
        self.assertEqual(rec["verdict"]["verdict"], "UNKNOWN")
        self.assertEqual(rec["official_sources"]["source"], "none")

    def test_green_contradicting_failed_original_is_rejected(self):
        rec = self.inspect([self.submit("GREEN", "x", cid=f"c{i}") for i in range(3)],
                           [], [{"status": "fail", "detail": "AttributeError"}])
        self.assertNotEqual(rec["verdict"]["verdict"], "GREEN")

    def test_red_backed_by_observed_failure_needs_no_web_citation(self):
        rec = self.inspect([call("submit_verdict", {"verdict": "RED", "reason": "설치 실패", "citations": []})],
                           [], [{"status": "fail", "detail": "AttributeError"}])
        self.assertEqual(rec["verdict"]["verdict"], "RED")
        self.assertEqual(rec["verdict"]["evidence_basis"], "observed-failure")

    def test_yellow_still_needs_official_citation(self):
        rec = self.inspect([call("submit_verdict", {"verdict": "YELLOW", "reason": "r", "citations": []}, f"c{i}") for i in range(3)],
                           [], [{"status": "ok", "detail": ""}])
        self.assertEqual(rec["verdict"]["verdict"], "UNKNOWN")
