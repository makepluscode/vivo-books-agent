import copy
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree

from drift import living, probe

GOOD_CODE = '''from langchain.agents import create_agent
from vivo_demo import make_model, weather

def answer_city(city):
    agent = create_agent(make_model(city), tools=[weather])
    state = agent.invoke({"messages": [{"role": "user", "content": city}]})
    return state["messages"][-1].content

print(answer_city("Seoul"))'''
DESCRIPTION = "create_agent builds an agent that actually calls tools."
EVIDENCE = {"title": "Official API", "url": "https://docs.langchain.com/oss/python/agents", "description": DESCRIPTION}
PLAN = {"verdict": "RED", "code": GOOD_CODE, "explanation_ko": "create_agent로 구성하고 메시지 객체를 invoke에 전달해요.",
        "citations": [{"evidence_id": "s1", "quote": DESCRIPTION}], "reason_ko": "목표 환경에서 구형 import 실패"}


def two_chapter_book(root, ids=("chapter03", "chapter07")):
    """기존 시나리오(영향 없는 3장 + 날씨 에이전트 7장)를 고정한 책. 샘플에 장이 늘어도 테스트가 흔들리지 않아요."""
    d = Path(root) / "_book"
    d.mkdir(parents=True, exist_ok=True)
    book = json.loads((living.SAMPLE / "book.json").read_text())
    book["chapters"] = [c for c in book["chapters"] if c["id"] in set(ids)]
    for name in [c["path"] for c in book["chapters"]] + [book["fixture"]]:
        (d / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(living.SAMPLE / name, d / name)
    (d / "book.json").write_text(json.dumps(book, ensure_ascii=False))
    return d / "book.json"


class FakeGateway:
    plans = []

    def __init__(self, output, emit):
        self.trace = []
        self.plans = copy.deepcopy(type(self).plans)

    def search(self, query):
        self.trace.append({"api": "Search", "mode": "test"})
        return [dict(EVIDENCE)]

    def agent(self, question):
        self.trace.append({"api": "Search Agent", "mode": "test"})
        return "Additional official evidence context", [dict(EVIDENCE)]

    def plan(self, payload, system=None):
        self.trace.append({"api": "Router", "mode": "test"})
        return self.plans.pop(0)


class LivingBookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.book = json.loads((living.SAMPLE / "book.json").read_text())
        cls.chapter = next(c for c in cls.book["chapters"] if c["id"] == "chapter07")
        cls.fixture = (living.SAMPLE / "examples/vivo_demo.py").read_text()

    def test_official_host_requires_exact_hostname_and_python_language(self):
        hosts = {"docs.langchain.com"}
        self.assertTrue(living.official_source(EVIDENCE, hosts))
        for url in ["https://docs.langchain.com.evil.test/a", "javascript:alert(1)",
                    "https://docs.langchain.com/oss/javascript/agents"]:
            self.assertFalse(living.official_source({"url": url}, hosts))

    def test_citation_must_quote_identified_snippet(self):
        sources = [{"id": "s1", **EVIDENCE}]
        self.assertTrue(living.citations_valid(PLAN, sources))
        for citations in [[], [{"evidence_id": "s99", "quote": DESCRIPTION}],
                          [{"evidence_id": "s1", "quote": "A fabricated removal claim"}],
                          [{"evidence_id": "s1", "quote": "agent"}]]:
            self.assertFalse(living.citations_valid({"citations": citations}, sources))

    @unittest.skipUnless(probe.sandbox_available(), "isolated target unavailable")
    def test_real_agent_calls_tools_for_independent_cities(self):
        result = living.verify(GOOD_CODE, self.chapter, self.fixture)
        self.assertEqual(result["status"], "ok", result)
        self.assertEqual(result["checks"], ["Busan: sunny, 22 C", "Jeju: sunny, 22 C"])
        self.assertEqual(result["tool_calls"], ["Seoul", "Busan", "Jeju"])
        self.assertTrue(result["agent_flow_verified"])
        self.assertTrue(result["tool_result_dependency_verified"])
        self.assertTrue(result["unseen_input_verified"])
        self.assertTrue(result["final_answer_verified"])
        observed = result["tool_result_observation"]
        self.assertEqual(observed["before"], "Busan: sunny, 22 C")
        self.assertTrue(observed["after"].startswith(observed["before"] + " | verification-"))

    @unittest.skipUnless(probe.sandbox_available(), "isolated target unavailable")
    def test_direct_tool_without_agent_does_not_pass(self):
        code = '''from vivo_demo import weather
def answer_city(city):
    return weather.invoke(city)
print(answer_city("Seoul"))'''
        result = living.verify(code, self.chapter, self.fixture)
        self.assertEqual(result["status"], "fail", result)
        self.assertFalse(result["agent_flow_verified"])

    @unittest.skipUnless(probe.sandbox_available(), "isolated target unavailable")
    def test_agent_called_but_tool_result_discarded_does_not_pass(self):
        code = GOOD_CODE.replace('return state["messages"][-1].content',
                                 'return city + ": sunny, 22 C"')
        result = living.verify(code, self.chapter, self.fixture)
        self.assertEqual(result["status"], "fail", result)
        self.assertFalse(result["tool_result_dependency_verified"])

    @unittest.skipUnless(probe.sandbox_available(), "isolated target unavailable")
    def test_code_tuned_to_listed_cities_is_rejected(self):
        code = GOOD_CODE.replace("def answer_city(city):\n",
                                 "def answer_city(city):\n    if city not in ['Seoul', 'Busan', 'Jeju']:\n        return 'WRONG'\n")
        result = living.verify(code, self.chapter, self.fixture)
        self.assertEqual(result["status"], "fail", result)
        self.assertTrue(result["tool_result_dependency_verified"])
        self.assertFalse(result["unseen_input_verified"])

    @unittest.skipUnless(probe.sandbox_available(), "isolated target unavailable")
    def test_returning_tool_message_instead_of_final_answer_is_rejected(self):
        code = GOOD_CODE.replace('state["messages"][-1]', 'state["messages"][-2]')
        result = living.verify(code, self.chapter, self.fixture)
        self.assertEqual(result["status"], "fail", result)
        self.assertTrue(result["unseen_input_verified"])
        self.assertFalse(result["final_answer_verified"])

    @unittest.skipUnless(probe.sandbox_available(), "isolated target unavailable")
    def test_factory_import_uses_same_observed_agent(self):
        code = GOOD_CODE.replace("from langchain.agents import", "from langchain.agents.factory import")
        self.assertEqual(living.verify(code, self.chapter, self.fixture)["status"], "ok")

    @unittest.skipUnless(probe.sandbox_available(), "isolated target unavailable")
    def test_preinjected_tool_message_is_not_agent_tool_execution(self):
        code = 'from langchain.agents import create_agent\nfrom langchain_core.messages import AIMessage, HumanMessage, ToolMessage\nfrom vivo_demo import make_model, weather\ndef answer_city(city):\n    out = weather.invoke(city)\n    agent = create_agent(make_model(city), tools=[weather])\n    state = agent.invoke({"messages": [HumanMessage(city),\n        AIMessage("", tool_calls=[{"name":"weather", "args":{"city":city}, "id":"weather-1", "type":"tool_call"}]),\n        ToolMessage(out, name="weather", tool_call_id="weather-1")]})\n    return state["messages"][-1].content\nprint(answer_city("Seoul"))'
        result = living.verify(code, self.chapter, self.fixture)
        self.assertEqual(result["status"], "fail", result)
        self.assertFalse(result["agent_flow_verified"])

    def test_candidate_cannot_import_observation_records(self):
        code = "from vivo_demo import model_inputs\nmodel_inputs.append([])"
        self.assertEqual(living.verify(code, self.chapter, self.fixture)["status"], "fail")

    def test_candidate_cannot_read_or_change_challenge(self):
        for name in ["weather_suffix", "_weather_suffix", "_set_weather_suffix", "_answer_suffix"]:
            code = "import vivo_demo\nprint(vivo_demo." + name + ")"
            self.assertEqual(living.verify(code, self.chapter, self.fixture)["status"], "fail")

    def test_offline_cache_miss_never_invokes_liner(self):
        with tempfile.TemporaryDirectory() as tmp:
            gateway = living.Gateway(Path(tmp), lambda e: None)
            gateway.allow_live = False
            with self.assertRaisesRegex(RuntimeError, "캐시가 없어"):
                gateway.request("Search", {"query": "missing"}, lambda: self.fail("live call"))

    @unittest.skipUnless(probe.sandbox_available(), "isolated target unavailable")
    def test_hardcoded_answer_does_not_pass_agent_verification(self):
        code = 'def answer_city(city):\n    return "Seoul: sunny, 22 C"\nprint(answer_city("Seoul"))'
        self.assertEqual(living.verify(code, self.chapter, self.fixture)["status"], "fail")

    def test_model_code_cannot_import_host_io(self):
        self.assertEqual(living.verify("import os\nprint(os.environ)", self.chapter, self.fixture)["status"], "fail")

    def test_example_files_match_the_manuscript_code(self):
        for chapter in self.book["chapters"]:
            if chapter.get("example"):
                md = (living.SAMPLE / chapter["path"]).read_text()
                self.assertEqual((living.SAMPLE / chapter["example"]).read_text().strip(), living.example(md).strip())

    def test_manuscript_rewrite_preserves_unmarked_content(self):
        original = (living.SAMPLE / "chapters/chapter07.md").read_text()
        updated = living.rewrite(original, PLAN)
        self.assertIn(GOOD_CODE, updated)
        self.assertIn("create_agent로 구성", updated)
        self.assertIn("날씨 도구는 고정된 값을 돌려줘요.", updated)
        self.assertEqual(living.example(original).count("create_react_agent("), 1)

    def test_local_path_cannot_escape_book(self):
        with self.assertRaises(ValueError):
            living.local_path(living.SAMPLE, "../../.env")

    def run_fake(self, output, plans, verifier, event=None):
        FakeGateway.plans = plans
        with patch.object(living, "Gateway", FakeGateway), patch.object(living, "verify", side_effect=verifier), patch.object(living.probe, "target_versions", return_value={"langchain": "test", "langchain-core": "test"}):
            return living.run(book_path=two_chapter_book(output), out_dir=output, event_path=event or living.DEMO_EVENT)

    @unittest.skipUnless(probe.sandbox_available(), "isolated target unavailable")
    def test_green_affected_chapter_preserves_manuscript_without_new_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_fake(Path(tmp), [{**PLAN, "verdict": "GREEN"}], lambda *a: {"status": "ok"})
            self.assertEqual(result["items"][1]["status"], "verified-unchanged")
            self.assertEqual(result["items"][1]["before_hash"], result["items"][1]["after_hash"])
            self.assertFalse(result["preview_created"])
            self.assertNotIn("보류", living.revision_summary_html(result))
            self.assertIn("변경 불필요", living.revision_summary_html(result))
            self.assertNotIn("· ok", living.revision_summary_html(result))
            self.assertEqual((Path(tmp) / "original.md").read_text(), (Path(tmp) / "revised.md").read_text())

    @unittest.skipUnless(probe.sandbox_available(), "isolated target unavailable")
    def test_red_with_successful_original_researches_once_then_preserves_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_fake(Path(tmp), [PLAN, PLAN], lambda *a: {"status": "ok"})
            item = result["items"][1]
            self.assertFalse(result["preview_created"])
            self.assertEqual(item["status_reason"], "verdict_execution_mismatch")
            self.assertEqual(item["before_hash"], item["after_hash"])
            self.assertEqual(sum(t["api"] == "Search Agent" for t in result["trace"]), 1)
            self.assertEqual(sum(t["api"] == "Router" for t in result["trace"]), 2)
            self.assertIn("원본 예제가 목표 환경에서 실행되는데", living.revision_summary_html(result))
            self.assertNotIn("· ok", living.revision_summary_html(result))

    @unittest.skipUnless(probe.sandbox_available(), "isolated target unavailable")
    def test_red_with_successful_original_can_be_reassessed_as_yellow(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_fake(Path(tmp), [PLAN, {**PLAN, "verdict": "YELLOW"}], lambda *a: {"status": "ok"})
            self.assertTrue(result["preview_created"])
            self.assertIn("권장 변경", living.revision_summary_html(result))
            self.assertEqual(sum(t["api"] == "Search Agent" for t in result["trace"]), 1)

    @unittest.skipUnless(probe.sandbox_available(), "isolated target unavailable")
    def test_yellow_with_successful_original_does_not_research(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_fake(Path(tmp), [{**PLAN, "verdict": "YELLOW"}], lambda *a: {"status": "ok"})
            self.assertTrue(result["preview_created"])
            self.assertFalse(any(t["api"] == "Search Agent" for t in result["trace"]))
            self.assertIn("권장 변경", living.revision_summary_html(result))

    @unittest.skipUnless(probe.sandbox_available(), "isolated target unavailable")
    def test_self_repair_cannot_replace_yellow_with_contradictory_red(self):
        sequence = iter([{"status": "ok"}, {"status": "fail", "error": "candidate failed"}])
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_fake(Path(tmp), [{**PLAN, "verdict": "YELLOW"}, PLAN], lambda *a: next(sequence))
            self.assertFalse(result["preview_created"])
            item = result["items"][1]
            self.assertEqual(item["plan"]["verdict"], "YELLOW")
            self.assertNotIn("self_repair", item)
            self.assertEqual(item["before_hash"], item["after_hash"])

    def test_unavailable_sandbox_holds_before_any_api_or_candidate_execution(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(probe, "sandbox_available", return_value=False):
            result = self.run_fake(Path(tmp), [], lambda *a: self.fail("candidate execution"))
            self.assertFalse(result["preview_created"])
            self.assertEqual(result["trace"], [])
            self.assertEqual(result["items"][1]["status_reason"], "sandbox_unavailable")
            page = (Path(tmp) / "reader.html").read_text()
            self.assertIn("실행 확인 보류", page)
            self.assertNotIn("실행 검증 실패", page)

    @unittest.skipUnless(probe.sandbox_available(), "isolated target unavailable")
    def test_original_policy_rejection_holds_before_api(self):
        before = living.verify("import json\n" + GOOD_CODE, self.chapter, self.fixture)
        self.assertEqual(before["status"], "fail")
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_fake(Path(tmp), [], lambda *a: before)
            self.assertEqual(result["trace"], [])
            item = result["items"][1]
            self.assertEqual(item["status_reason"], "original_outside_contract")
            self.assertIn("개정 미리보기를 만들지 않았어요", living.evidence_html(result))
            self.assertEqual(item["before_hash"], item["after_hash"])
            self.assertNotIn("<b>문제:</b>", living.revision_summary_html(result))

    @unittest.skipUnless(probe.sandbox_available(), "isolated target unavailable")
    def test_original_stream_contract_rejection_holds_before_api(self):
        code = GOOD_CODE.replace('state = agent.invoke({"messages": [{"role": "user", "content": city}]})',
                                 'state = list(agent.stream({"messages": [{"role": "user", "content": city}]}, stream_mode="values"))[-1]')
        before = living.verify(code, self.chapter, self.fixture)
        self.assertEqual(living.original_failure_kind(before, self.chapter), "contract", before)
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_fake(Path(tmp), [], lambda *a: before)
            self.assertFalse(result["preview_created"])
            self.assertEqual(result["trace"], [])
            self.assertEqual(result["items"][1]["before_hash"], result["items"][1]["after_hash"])
            self.assertNotIn("<b>문제:</b>", living.revision_summary_html(result))

    def test_missing_target_package_holds_before_api_and_execution(self):
        FakeGateway.plans = []
        for versions in [{"langchain": None, "langchain-core": "test"}, {"langchain": "test", "langchain-core": None}, {}]:
            with tempfile.TemporaryDirectory() as tmp, patch.object(living, "Gateway", FakeGateway), patch.object(probe, "sandbox_available", return_value=True), patch.object(probe, "target_versions", return_value=versions), patch.object(living, "verify", side_effect=AssertionError("must not execute")):
                result = living.run(book_path=two_chapter_book(tmp), out_dir=Path(tmp))
                self.assertFalse(result["preview_created"])
                self.assertEqual(result["trace"], [])
                self.assertEqual(result["items"][1]["status_reason"], "target_package_missing")
                self.assertNotIn("<b>문제:</b>", living.revision_summary_html(result))

    @unittest.skipUnless(probe.sandbox_available(), "isolated target unavailable")
    def test_original_observation_contract_failure_is_not_runtime_failure(self):
        before = {"status": "fail", "stdout": self.chapter["expected_stdout"],
                  "checks": [c["expected"] for c in self.chapter["checks"]],
                  "agent_flow_verified": False, "tool_result_dependency_verified": True}
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_fake(Path(tmp), [], lambda *a: before)
            self.assertEqual(result["trace"], [])
            self.assertEqual(result["items"][1]["status_reason"], "original_outside_contract")

    @unittest.skipUnless(probe.sandbox_available(), "isolated target unavailable")
    def test_original_timeout_holds_before_api_with_specific_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_fake(Path(tmp), [], lambda *a: {"status": "timeout", "error": "time limit"})
            self.assertFalse(result["preview_created"])
            self.assertEqual(result["trace"], [])
            self.assertEqual(result["items"][1]["status_reason"], "original_execution_timeout")
            page = (Path(tmp) / "reader.html").read_text()
            self.assertIn("실행 시간 초과로 확인 보류", page)
            self.assertNotIn("검토 위치: ·", page)

    @unittest.skipUnless(probe.sandbox_available(), "isolated target unavailable")
    def test_wrong_return_format_is_runtime_and_repaired_instead_of_hidden(self):
        code = GOOD_CODE.replace('return state["messages"][-1].content',
                                 'return state.get("output")')
        before = living.verify(code, self.chapter, self.fixture)
        self.assertEqual(before["stdout"], "None")
        self.assertEqual(living.original_failure_kind(before, self.chapter), "runtime")
        after = living.verify(GOOD_CODE, self.chapter, self.fixture)
        sequence = iter([before, after])
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_fake(Path(tmp), [PLAN], lambda *a: next(sequence))
            self.assertTrue(result["preview_created"])
            self.assertEqual(result["items"][1]["status"], "verified-change")
            self.assertEqual(result["items"][1]["original_failure_kind"], "runtime")
            self.assertEqual(sum(t["api"] == "Router" for t in result["trace"]), 1)
            self.assertIn("출력 불일치", living.revision_summary_html(result))
            self.assertIn("실제 None", living.revision_summary_html(result))

    @unittest.skipUnless(probe.sandbox_available(), "isolated target unavailable")
    def test_partial_migration_run_error_preserves_real_graph_error(self):
        code = GOOD_CODE.replace('state = agent.invoke({"messages": [{"role": "user", "content": city}]})',
                                 'state = agent.run(city)')
        before = living.verify(code, self.chapter, self.fixture)
        self.assertEqual(before["status"], "fail")
        self.assertIn("CompiledStateGraph", before["error"])
        self.assertIn("has no attribute 'run'", before["error"])
        self.assertNotIn("_ObservedAgent", before["error"])
        self.assertEqual(living.original_failure_kind(before, self.chapter), "runtime")
        after = living.verify(GOOD_CODE, self.chapter, self.fixture)
        sequence = iter([before, after])
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_fake(Path(tmp), [PLAN], lambda *a: next(sequence))
            self.assertTrue(result["preview_created"])
            self.assertEqual(result["items"][1]["original_failure_kind"], "runtime")

    @unittest.skipUnless(probe.sandbox_available(), "isolated target unavailable")
    def test_single_batch_uses_observed_invoke_without_losing_graph_identity(self):
        code = GOOD_CODE.replace('state = agent.invoke({"messages": [{"role": "user", "content": city}]})',
                                 'state = agent.batch([{"messages": [{"role": "user", "content": city}]}])[0]')
        result = living.verify(code, self.chapter, self.fixture)
        self.assertEqual(result["status"], "ok", result)
        self.assertTrue(result["agent_flow_verified"])
        self.assertTrue(result["tool_result_dependency_verified"])

    @unittest.skipUnless(probe.sandbox_available(), "isolated target unavailable")
    def test_graph_introspection_delegates_without_changing_execution(self):
        code = GOOD_CODE.replace('state = agent.invoke', 'agent.get_graph()\n    state = agent.invoke')
        self.assertEqual(living.verify(code, self.chapter, self.fixture)["status"], "ok")

    @unittest.skipUnless(probe.sandbox_available(), "isolated target unavailable")
    def test_timeout_error_is_explicit_and_not_stderr_warning(self):
        with patch.object(probe, "sandbox_available", return_value=True), patch.object(probe, "_sandboxed", return_value=(124, True, "", "if asyncio.iscoroutinefunction(func):")):
            before = living.verify(GOOD_CODE, self.chapter, self.fixture)
        self.assertEqual(before["error"], "실행 시간 초과(30초)")
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_fake(Path(tmp), [], lambda *a: before)
            for name in ["reader.html", "revision.json"]:
                text = (Path(tmp) / name).read_text()
                self.assertIn("실행 시간 초과(30초)", text)
                self.assertNotIn("iscoroutinefunction", text)
            self.assertEqual(result["trace"], [])

    @unittest.skipUnless(probe.sandbox_available(), "isolated target unavailable")
    def test_lcel_pipe_preserves_real_runnable_execution(self):
        code = GOOD_CODE.replace('state = agent.invoke({"messages": [{"role": "user", "content": city}]})\n    return state["messages"][-1].content',
            'chain = agent | (lambda state: state["messages"][-1].content)\n    return chain.invoke({"messages": [{"role": "user", "content": city}]})')
        result = living.verify(code, self.chapter, self.fixture)
        self.assertEqual(result["status"], "ok", result)
        self.assertTrue(result["agent_flow_verified"])
        self.assertTrue(result["tool_result_dependency_verified"])

    @unittest.skipUnless(probe.sandbox_available(), "isolated target unavailable")
    def test_agent_preserves_runnable_type_identity(self):
        code = 'from langchain_core.runnables import Runnable\n' + GOOD_CODE.replace(
            'state = agent.invoke', 'assert isinstance(agent, Runnable)\n    state = agent.invoke')
        self.assertEqual(living.verify(code, self.chapter, self.fixture)["status"], "ok")

    @unittest.skipUnless(probe.sandbox_available(), "isolated target unavailable")
    def test_normal_lcel_original_is_not_changed_by_red_verdict(self):
        code = GOOD_CODE.replace('state = agent.invoke({"messages": [{"role": "user", "content": city}]})\n    return state["messages"][-1].content',
            'chain = agent | (lambda state: state["messages"][-1].content)\n    return chain.invoke({"messages": [{"role": "user", "content": city}]})')
        before = living.verify(code, self.chapter, self.fixture)
        self.assertEqual(before["status"], "ok")
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_fake(Path(tmp), [PLAN, PLAN], lambda *a: before)
            self.assertFalse(result["preview_created"])
            self.assertEqual(result["items"][1]["status_reason"], "verdict_execution_mismatch")
            self.assertEqual(result["items"][1]["before_hash"], result["items"][1]["after_hash"])

    def test_unrelated_release_never_calls_model_or_verifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            event = Path(tmp) / "event.json"
            event.write_text(json.dumps({"action": "published", "repository": {"full_name": "other/sdk"}, "release": {}}))
            result = self.run_fake(Path(tmp) / "run", [], lambda *a: self.fail("unrelated chapter executed"), event)
            self.assertFalse(result["preview_created"])
            self.assertEqual(result["trace"], [])
            self.assertTrue(all(i["status"] == "unchanged" for i in result["items"]))

    def test_detected_repositories_all_select_their_chapters(self):
        with tempfile.TemporaryDirectory() as tmp:
            book_path = two_chapter_book(tmp)
            release = json.loads((living.DEMO_EVENT).read_text())
            release["detected"] = [{"repository": "ollama/ollama"}]
            event_path = Path(tmp) / "event.json"
            event_path.write_text(json.dumps(release))
            with patch.object(living.probe, "sandbox_available", return_value=False):
                result = living.run(book_path=book_path, event_path=event_path, out_dir=Path(tmp))
        self.assertEqual([i["status"] for i in result["items"]], ["blocked-environment", "blocked-environment"])

    @unittest.skipUnless(probe.sandbox_available(), "isolated target unavailable")
    def test_bad_citation_blocks_preview_and_removes_stale_artifact(self):
        bad = {**PLAN, "citations": [{"evidence_id": "s1", "quote": "invented missing text"}]}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "preview.epub").write_bytes(b"old success")
            result = self.run_fake(out, [bad, bad], lambda *a: {"status": "fail", "error": "old import failed"})
            self.assertFalse(result["preview_created"])
            self.assertFalse((out / "preview.epub").exists())
            self.assertIn("blocked-evidence", [i["status"] for i in result["items"]])
            self.assertEqual(result["items"][1]["status_reason"], "citations_invalid")
            self.assertIn("인용문을 공식 검색 결과에서 확인하지 못해", (out / "reader.html").read_text())
            self.assertIn('id="epub" hidden', (out / "reader.html").read_text())
            self.assertIn("인용 대조 실패 · 적용 보류", living.evidence_html(result))

    @unittest.skipUnless(probe.sandbox_available(), "isolated target unavailable")
    def test_verified_preview_contains_changed_and_unchanged_chapters(self):
        sequence = iter([{"status": "fail", "error": "old import failed"}, {"status": "ok", "stdout": "Seoul: sunny, 22 C"}])
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            result = self.run_fake(out, [PLAN], lambda *a: next(sequence))
            self.assertTrue(result["preview_created"])
            unchanged = result["items"][0]
            self.assertEqual(unchanged["before_hash"], unchanged["after_hash"])
            with zipfile.ZipFile(out / "preview.epub") as z:
                self.assertEqual(z.infolist()[0].filename, "mimetype")
                for name in z.namelist():
                    if name.endswith((".xml", ".xhtml", ".opf")):
                        ElementTree.fromstring(z.read(name))
                self.assertIn(b"create_agent", z.read("OEBPS/chapter07.xhtml"))
                self.assertIn(b'print(model)', z.read("OEBPS/chapter03.xhtml"))
                notes = z.read("OEBPS/revision-notes.xhtml").decode()
                self.assertIn("docs.langchain.com", notes)
                self.assertIn("저자 검토 전", notes)
                self.assertIn("외부 LLM·날씨 API", notes)
                self.assertEqual(unchanged["before_epub_hash"], unchanged["after_epub_hash"])
                visible = living.evidence_html(result)
                self.assertIn(DESCRIPTION, visible)
                self.assertIn("설명 문단 1곳", visible)
                self.assertIn("EPUB 장 파일 동일", visible)
                with zipfile.ZipFile(out / "original.epub") as baseline:
                    self.assertEqual(z.read("OEBPS/chapter03.xhtml"), baseline.read("OEBPS/chapter03.xhtml"))

    @unittest.skipUnless(probe.sandbox_available(), "isolated target unavailable")
    def test_failed_candidate_is_repaired_once_then_validated(self):
        sequence = iter([{"status": "fail"}, {"status": "fail", "error": "bad candidate"}, {"status": "ok"}])
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_fake(Path(tmp), [PLAN, PLAN], lambda *a: next(sequence))
            self.assertTrue(result["preview_created"])
            self.assertTrue(result["items"][1]["self_repair"])

    @unittest.skipUnless(probe.sandbox_available(), "isolated target unavailable")
    def test_unknown_gets_one_agent_research_then_grounded_reassessment(self):
        sequence = iter([{"status": "fail"}, {"status": "ok"}])
        unknown = {"verdict": "UNKNOWN", "citations": [], "reason_ko": "insufficient evidence"}
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_fake(Path(tmp), [unknown, PLAN], lambda *a: next(sequence))
            self.assertTrue(result["preview_created"])
            self.assertTrue(result["items"][1]["additional_research"])
            self.assertEqual(sum(t["api"] == "Search Agent" for t in result["trace"]), 1)
            self.assertEqual(sum(t["api"] == "Router" for t in result["trace"]), 2)

    @unittest.skipUnless(probe.sandbox_available(), "isolated target unavailable")
    def test_unknown_after_research_keeps_original_and_explains_hold(self):
        unknown = {"verdict": "UNKNOWN", "citations": [], "reason_ko": "insufficient evidence"}
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_fake(Path(tmp), [unknown, unknown], lambda *a: {"status": "fail"})
            item = result["items"][1]
            self.assertFalse(result["preview_created"])
            self.assertEqual(item["status_reason"], "UNKNOWN")
            self.assertEqual(item["before_hash"], item["after_hash"])
            self.assertEqual(sum(t["api"] == "Search Agent" for t in result["trace"]), 1)
            self.assertIn("추가 조사 후에도", (Path(tmp) / "reader.html").read_text())
            self.assertIn("적용 보류", living.evidence_html(result))

    @unittest.skipUnless(probe.sandbox_available(), "isolated target unavailable")
    def test_failed_candidate_none_results_still_produces_hold_reader(self):
        failed = {"status": "fail", "stdout": "", "checks": [None, None], "tool_calls": []}
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_fake(Path(tmp), [PLAN, PLAN], lambda *a: failed)
            self.assertFalse(result["preview_created"])
            page = (Path(tmp) / "reader.html").read_text()
            self.assertIn("실행 검증 실패", page)
            self.assertIn("적용 보류", page)
            self.assertTrue((Path(tmp) / "revision.json").exists())

    @unittest.skipUnless(probe.sandbox_available(), "isolated target unavailable")
    def test_missing_search_title_still_produces_hold_reader(self):
        bad = {**PLAN, "citations": [{"evidence_id": "s1", "quote": "invented missing text"}]}
        with tempfile.TemporaryDirectory() as tmp, patch.dict(EVIDENCE, {"title": None}):
            result = self.run_fake(Path(tmp), [bad, bad], lambda *a: {"status": "fail"})
            self.assertFalse(result["preview_created"])
            self.assertIn(EVIDENCE["url"], (Path(tmp) / "reader.html").read_text())

    @unittest.skipUnless(probe.sandbox_available(), "isolated target unavailable")
    def test_malformed_citations_still_produces_hold_reader(self):
        bad = {**PLAN, "citations": "wrong type"}
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_fake(Path(tmp), [bad, bad], lambda *a: {"status": "fail"})
            self.assertFalse(result["preview_created"])
            page = (Path(tmp) / "reader.html").read_text()
            self.assertIn("적용 보류", page)
            self.assertIn("인용문을 공식 검색 결과에서 확인하지 못해", page)

    def test_reader_escapes_script_in_generated_prose(self):
        md = '# Demo\n</script><img src=x onerror=alert(1)>'
        result = {"items": [], "preview_created": False}
        page = living.reader_html(self.book, [(self.chapter, md)], [(self.chapter, md)], result)
        self.assertNotIn('</script><img', page)
        self.assertIn('\\u003c', page)


if __name__ == "__main__":
    unittest.main()


class StdoutContractTests(unittest.TestCase):
    """범용 출력 계약(4장): 실제 격리 실행으로 확인해요."""
    @classmethod
    def setUpClass(cls):
        book = json.loads((living.SAMPLE / "book.json").read_text())
        cls.chapter = next(c for c in book["chapters"] if c["id"] == "chapter04")
        cls.fixture = (living.SAMPLE / "examples/vivo_demo.py").read_text()
        cls.original = living.example((living.SAMPLE / "chapters/chapter04.md").read_text())
        cls.fixed = cls.original.replace("from langchain.prompts import", "from langchain_core.prompts import")

    def setUp(self):
        if not probe.sandbox_available():
            self.skipTest("격리 환경 없음")

    def test_original_fails_as_runtime_and_fix_passes(self):
        before = living.verify(self.original, self.chapter, self.fixture)
        self.assertEqual(before["status"], "fail")
        self.assertIn("langchain.prompts", before["error"])
        self.assertEqual(living.original_failure_kind(before, self.chapter), "runtime")
        after = living.verify(self.fixed, self.chapter, self.fixture)
        self.assertEqual(after["status"], "ok")
        self.assertTrue(after["input_dependency_verified"])
        self.assertTrue(after["prompt_chain_verified"])
        self.assertTrue(after["runnable_chain_verified"])

    def test_prompt_dropped_for_unseen_question_is_rejected(self):
        code = self.fixed.replace("def ask(question):\n", "def ask(question):\n"
                                  "    if question not in ['서울 날씨는?', '부산 날씨는?']:\n"
                                  "        return (ChatPromptTemplate.from_template('{question}') | llm | output_parser)"
                                  ".invoke({'question': question})\n")
        result = living.verify(code, self.chapter, self.fixture)
        self.assertEqual(result["status"], "fail", result)
        self.assertFalse(result["input_dependency_verified"])

    def test_steps_called_without_the_runnable_chain_are_rejected(self):
        code = self.fixed.replace('return chain.invoke({"question": question})',
                                  'return output_parser.invoke(llm.invoke(prompt.invoke({"question": question})))')
        result = living.verify(code, self.chapter, self.fixture)
        self.assertEqual(result["status"], "fail", result)
        self.assertTrue(result["prompt_chain_verified"])
        self.assertFalse(result["runnable_chain_verified"])

    def test_answer_ignoring_input_is_rejected(self):
        code = self.fixed.replace('return chain.invoke({"question": question})',
                                  'return chain.invoke({"question": "부산 날씨는?" if "부산" in question else "서울 날씨는?"})')
        result = living.verify(code, self.chapter, self.fixture)
        self.assertEqual(result["status"], "fail")
        self.assertFalse(result["input_dependency_verified"])

    def test_echoing_input_without_the_prompt_chain_is_rejected(self):
        code = self.fixed.replace('return chain.invoke({"question": question})',
                                  'return "도우미 답변 ← 당신은 날씨를 쉽게 설명하는 도우미예요. 다음 질문에 짧게 답해 주세요. 질문: " + question')
        result = living.verify(code, self.chapter, self.fixture)
        self.assertEqual(result["status"], "fail")
        self.assertTrue(result["input_dependency_verified"])
        self.assertFalse(result["prompt_chain_verified"])

    def test_fixture_internals_stay_hidden(self):
        code = self.fixed.replace("from vivo_demo import make_chat_model", "from vivo_demo import make_chat_model, model_inputs")
        self.assertEqual(living.verify(code, self.chapter, self.fixture)["status"], "fail")

    def test_three_chapter_book_revises_both_affected_chapters(self):
        plans = {"chapter04": {"verdict": "RED", "code": self.fixed, "explanation_ko": "langchain_core.prompts에서 가져와요.",
                               "citations": [{"evidence_id": "s1", "quote": DESCRIPTION}], "reason_ko": "import 실패"},
                 "chapter07": PLAN}
        FakeGateway.plans = [plans["chapter04"], plans["chapter07"]]
        verdicts = iter([{"status": "fail", "error": "ModuleNotFoundError"}, {"status": "ok"},
                         {"status": "fail", "error": "ImportError"}, {"status": "ok"}])
        with tempfile.TemporaryDirectory() as tmp, patch.object(living, "Gateway", FakeGateway), \
                patch.object(living, "verify", side_effect=lambda *a: next(verdicts)), \
                patch.object(living.probe, "target_versions", return_value={"langchain": "test", "langchain-core": "test"}):
            result = living.run(book_path=two_chapter_book(tmp, ("chapter03", "chapter04", "chapter07")), out_dir=Path(tmp))
            self.assertTrue(result["preview_created"])
            self.assertEqual([i["status"] for i in result["items"]], ["unchanged", "verified-change", "verified-change"])
            revised = (Path(tmp) / "revised.md").read_text()
            self.assertIn("from langchain_core.prompts import", revised)
            self.assertIn(GOOD_CODE, revised)


class ProseChapterTests(unittest.TestCase):
    """본문 장: 버전 동기화(확정적) + API 설명 문장(에이전트, 공식 인용 필요)."""
    PINS = {"langchain": "0.3.25", "langchain-core": "0.3.61"}
    TARGET = {"langchain": "1.5.0", "langchain-core": "1.8.1"}

    def test_sync_versions_only_touches_pinned_versions(self):
        md = "LangChain 0.3.25, langchain-core 0.3.61 기준\npip install langchain==0.3.25 langchain-core==0.3.61 pandas==1.5.3\nlangchain 0.3.250은 없어요"
        md += "\n과거에는 LangChain 0.3.25를 사용했어요."
        new, changes = living.sync_versions(md, self.PINS, self.TARGET, version_lines=[1])
        self.assertIn("LangChain 1.5.0, langchain-core 1.8.1 기준", new)
        self.assertIn("pip install langchain==1.5.0 langchain-core==1.8.1 pandas==1.5.3", new)
        self.assertIn("0.3.250", new)
        self.assertIn("과거에는 LangChain 0.3.25를 사용했어요.", new)
        self.assertEqual([c["kind"] for c in changes], ["sentence", "pip"])

    def run_prose(self, verdicts, required=(), installable=True, include_chapter4=False, local=()):
        md = (living.SAMPLE / "chapters/chapter01.md").read_text()
        lines = md.splitlines()
        api_line = next(n for n, line in enumerate(lines, 1) if "AgentExecutor" in line)
        items = [{"id": "s7", "lines": [api_line, api_line], "kind": "sentence", "subject": "7장 소개", "packages": ["langchain"]}]
        if include_chapter4:
            items.insert(0, {**items[0], "id": "s4", "lines": [13, 13]})
        recs = iter(verdicts)

        class G:
            def router_json(self, system, user):
                return [items, ""]
        with patch("drift.pipeline.extract", return_value=items), \
                patch.object(living.agent, "inspect_item", side_effect=lambda *a, **k: next(recs)), \
                patch.object(living.probe, "pip_check", return_value={"langchain==1.5.0": {"installable": installable}, "langchain-core==1.8.1": {"installable": installable}}):
            chapter = {"id": "chapter01", "version_lines": [5], "required_prose_lines": required, "local_prose_lines": local}
            return living.revise_prose(chapter, md, self.TARGET, self.PINS, [], G(), lambda e: None)

    def test_cited_sentence_fix_is_applied_with_version_sync(self):
        fix = "7장에서는 `create_agent()`로 에이전트를 만들고 `invoke()`로 실행해요."
        rec = {"verdict": {"verdict": "YELLOW", "fix": fix, "reason": "r", "evidence_basis": "official-citation",
                           "citations": [{"official": True, "url": EVIDENCE["url"], "quote": DESCRIPTION, "quote_found": True}]},
               "evidence": [dict(EVIDENCE)], "agent": {}}
        item, new_md = self.run_prose([rec])
        self.assertEqual(item["status"], "verified-change")
        self.assertIn(fix, new_md)
        self.assertIn("pip install langchain==1.5.0", new_md)
        self.assertIn("이 개정판의 실습 기준은 LangChain 1.5.0", new_md)
        self.assertTrue(item["citations_valid"])
        self.assertEqual(len(item["change_locations"]), 3)

    def test_uncited_sentence_is_held_but_versions_still_sync(self):
        rec = {"verdict": {"verdict": "UNKNOWN", "fix": None, "reason": "근거 부족", "citations": []}, "evidence": [], "agent": {}}
        item, new_md = self.run_prose([rec])
        self.assertIn("AgentExecutor", new_md)
        self.assertIn("LangChain 1.5.0", new_md)
        self.assertFalse(item["prose_changes"][-1]["applied"])

    def test_book_local_lines_are_not_researched(self):
        md = (living.SAMPLE / "chapters/chapter01.md").read_text()
        api_line = next(n for n, line in enumerate(md.splitlines(), 1) if "AgentExecutor" in line)
        item, new_md = self.run_prose([], local=[api_line])
        self.assertEqual([c["line"] for c in item["prose_changes"] if c.get("kind") == "sentence" and c.get("verdict")], [])
        self.assertIn("AgentExecutor", new_md)

    def test_required_sentence_without_evidence_blocks_revision(self):
        rec = {"verdict": {"verdict": "UNKNOWN", "fix": None, "citations": []}, "evidence": []}
        item, new_md = self.run_prose([rec], required=[15])
        self.assertEqual(item["status"], "blocked-evidence")
        self.assertEqual(new_md, (living.SAMPLE / "chapters/chapter01.md").read_text())

    def test_unverified_install_blocks_revision_before_model_use(self):
        item, new_md = self.run_prose([], installable=None)
        self.assertEqual(item["status"], "blocked-execution")
        self.assertEqual(new_md, (living.SAMPLE / "chapters/chapter01.md").read_text())

    def test_multiline_edit_keeps_other_source_ranges_in_place(self):
        def record(fix):
            quote = fix + " 근거 문장이에요."
            return {"verdict": {"verdict": "YELLOW", "fix": fix, "evidence_basis": "official-citation",
                                "citations": [{"official": True, "url": EVIDENCE["url"], "quote": quote, "quote_found": True}]},
                    "evidence": [{**EVIDENCE, "description": quote}]}
        item, new_md = self.run_prose([record("4장 첫 문장\n4장 둘째 문장"), record("7장 새 문장")],
                                     required=[13, 15], include_chapter4=True)
        self.assertEqual(item["status"], "verified-change")
        self.assertIn("4장 첫 문장\n4장 둘째 문장\n\n7장 새 문장", new_md)
        self.assertIn("각 장의 예제는", new_md)
