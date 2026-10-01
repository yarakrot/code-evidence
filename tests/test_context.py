import json
import tempfile
import unittest
from pathlib import Path

from code_evidence.context import build_context


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_symbol_and_call_relationships(self):
        self.write(
            "export.py",
            "def format_time(n):\n    return str(n)\n\n"
            "def export_subtitles(n):\n    return format_time(n)\n",
        )
        report = build_context(self.root, "export_subtitles")
        by_name = {f["symbol"]: f for f in report["fragments"]}
        self.assertIn("export_subtitles", by_name)
        self.assertIn("format_time", by_name)
        self.assertEqual(by_name["export_subtitles"]["start_line"], 4)
        self.assertTrue(any("callee" in r for r in by_name["format_time"]["reasons"]))

    def test_budget_includes_json_metadata_and_unicode(self):
        self.write(
            "module.py",
            "\n".join(f"def example_{i}():\n    return 'Пример {i}'" for i in range(30)),
        )
        result = build_context(self.root, "example", 2000)
        actual = len(json.dumps(result, ensure_ascii=True, separators=(",", ":")).encode())
        self.assertLessEqual(actual, 2000)
        self.assertEqual(result["serialized_bytes"], actual)
        self.assertGreater(result["coverage"]["omitted_matches"], 0)

    def test_no_stale_index_after_edit(self):
        self.write("sample.py", "def target():\n    return 1\n")
        before = build_context(self.root, "target")
        self.write("sample.py", "def target():\n    return 2\n")
        after = build_context(self.root, "target")
        self.assertNotEqual(before["snapshot_digest"], after["snapshot_digest"])
        self.assertIn("return 2", after["fragments"][0]["text"])

    def test_target_not_executed_and_secrets_redacted(self):
        token = "sk-" + "x" * 24
        self.write(
            "sample.py",
            f"raise RuntimeError('must not execute')\ndef target():\n    return '{token}'\n",
        )
        self.write(".env", "secret")
        result = build_context(self.root, "target")
        self.assertNotIn(token, json.dumps(result))
        self.assertIn("[REDACTED]", result["fragments"][0]["text"])

    def test_invalid_python_and_no_matches_are_explicit(self):
        self.write("broken.py", "def invalid(:\n")
        result = build_context(self.root, "unrelated")
        self.assertEqual(result["fragments"], [])
        self.assertFalse(result["coverage"]["index_complete"])

    def test_bad_inputs_rejected(self):
        for task, budget in (
            ("", 2000),
            ("fix the code", 2000),
            ("target", 100),
            ("target", True),
            ("x" * 2001, 2000),
        ):
            with self.assertRaises(ValueError):
                build_context(self.root, task, budget)

    def test_primary_oversized_symbol_returns_explicit_partial_range(self):
        self.write("sample.py", "def target():\n" + "    value = 'example'\n" * 300)
        result = build_context(self.root, "target", 2000)
        first = result["fragments"][0]
        self.assertTrue(first["fragment_truncated"])
        self.assertLess(first["end_line"], first["symbol_end_line"])
        self.assertEqual(len(first["text"].splitlines()), first["end_line"])
        self.assertLessEqual(result["serialized_bytes"], 2000)

    def test_classes_do_not_duplicate_selected_method_ranges(self):
        self.write("sample.py", "class Exporter:\n    def target(self):\n        return 1\n")
        result = build_context(self.root, "target")
        self.assertEqual(len(result["fragments"]), 1)
