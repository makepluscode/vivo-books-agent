"""장 점검(drift/pipeline.py)의 원고 파싱·입력 정규화 단위 테스트 — Liner 호출 없음."""
import unittest

from drift import liner, pipeline, probe, report


class CodeBlocksTest(unittest.TestCase):
    def test_closing_fence_of_other_language_is_not_python(self):
        lines = ["t", "```bash", "pip install x", "```", "본문 문장", "```python", "x = 1", "```"]
        self.assertEqual(pipeline.code_blocks(lines), [(7, 7)])

    def test_untagged_and_python_blocks(self):
        lines = ["```", "a = 1", "```", "```py", "b = 2", "c = 3", "```", "```yaml", "k: v", "```"]
        self.assertEqual(pipeline.code_blocks(lines), [(2, 2), (5, 6)])


class NormLinesTest(unittest.TestCase):
    def test_reversed_and_out_of_range_spans(self):
        self.assertEqual(pipeline.norm_lines([20, 15], 30), [15, 20])
        self.assertEqual(pipeline.norm_lines([0, 99], 30), [1, 30])
        self.assertEqual(pipeline.norm_lines([12], 30), [12, 12])
        self.assertEqual(pipeline.norm_lines(12, 30), [12, 12])

    def test_unusable_spans(self):
        self.assertIsNone(pipeline.norm_lines(["12-15"], 30))
        self.assertIsNone(pipeline.norm_lines([40, 50], 30))
        self.assertIsNone(pipeline.norm_lines({"a": 1}, 30))


class PipSpecsTest(unittest.TestCase):
    def test_each_line_is_parsed_separately(self):
        self.assertEqual(probe.pip_specs("pip install langchain==0.3.25\npip install openai==1.0"),
                         ["langchain==0.3.25", "openai==1.0"])
        self.assertEqual(probe.pip_specs("pip install a==1 \\\n  b==2"), ["a==1", "b==2"])

    def test_other_commands_are_skipped(self):
        self.assertEqual(probe.pip_specs("pip install a==1\nros2 run turtlesim turtlesim_node"), [])
        self.assertEqual(probe.pip_specs("pip install -r requirements.txt"), [])


class ParseJsonTest(unittest.TestCase):
    def test_fenced_reply_with_trailing_brackets(self):
        self.assertEqual(liner.parse_json('```json\n{"verdict": "RED"}\n```\n근거 [1] 참고'), {"verdict": "RED"})

    def test_plain_reply_is_unchanged(self):
        self.assertEqual(liner.parse_json('[{"id": "a"}]'), [{"id": "a"}])
        with self.assertRaises(ValueError):
            liner.parse_json("JSON이 없는 답")


class ReportNullFieldsTest(unittest.TestCase):
    def test_null_reason_and_citations(self):
        result = {"target": "langchain==1.5.0", "items": [
            {"item": {"id": "i1", "lines": [3, 3], "subject": "import"},
             "verdict": {"verdict": "YELLOW", "reason": None, "citations": None, "fix": None}}]}
        self.assertIn("3–3줄", report.errata_md(result, "chapter.md"))


if __name__ == "__main__":
    unittest.main()
