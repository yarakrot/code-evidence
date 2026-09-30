import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from code_evidence.diagnostics import summarize
from code_evidence.policy import Check, load_checks
from code_evidence.runner import execute
from code_evidence.service import EvidenceService
from code_evidence.snapshot import snapshot


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.write("app.py", "print('hello')\n")
        self.policy(["{python}", "app.py"])

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def policy(self, argv, timeout=10):
        self.write(
            "code-evidence.toml",
            "schema_version = 1\n[checks.tests]\n"
            f"argv = {json.dumps(argv)}\ntimeout_seconds = {timeout}\n",
        )

    def test_read_only_service_never_executes(self):
        service = EvidenceService(self.root)
        with self.assertRaises(ValueError):
            service.run_checks(["tests"])
        self.assertIsNone(service.store.get())
        self.assertFalse(service.inspect_change()["execution_enabled"])

    def test_success_receipt_and_source_staleness(self):
        service = EvidenceService(self.root, True)
        result = service.run_checks(["tests"])
        self.assertEqual(result["freshness"], "fresh")
        self.assertEqual(result["results"][0]["status"], "passed")
        self.write("app.py", "print('changed')\n")
        later = service.get_run_summary(result["run_id"])
        self.assertEqual(later["freshness"], "stale")
        self.assertEqual(later["changed_files"]["modified"], ["app.py"])

    def test_failure_retains_exit_code_and_evidence(self):
        self.write("app.py", "raise AssertionError('synthetic failure')\n")
        service = EvidenceService(self.root, True)
        result = service.run_checks(["tests"])
        self.assertEqual(result["results"][0]["status"], "failed")
        self.assertNotEqual(result["results"][0]["exit_code"], 0)
        self.assertTrue(result["results"][0]["diagnostics"])
        fragment = service.read_evidence(result["run_id"], "tests")
        self.assertIn("AssertionError", fragment["text"])

    def test_no_unconfigured_or_duplicate_check(self):
        service = EvidenceService(self.root, True)
        for names in (["unknown"], [], ["tests", "tests"]):
            with self.assertRaises(ValueError):
                service.run_checks(names)

    def test_policy_frozen_for_server_lifetime(self):
        service = EvidenceService(self.root, True)
        self.policy(["{python}", "-c", "raise RuntimeError('changed policy')"])
        result = service.run_checks(["tests"])
        self.assertEqual(result["results"][0]["status"], "passed")
        reloaded = EvidenceService(self.root, True)
        self.assertEqual(reloaded.get_run_summary(result["run_id"])["freshness"], "stale")

    def test_source_mutation_during_check_is_stale(self):
        self.write("app.py", "from pathlib import Path\nPath('generated.txt').write_text('new')\n")
        result = EvidenceService(self.root, True).run_checks(["tests"])
        self.assertEqual(result["freshness"], "stale")

    def test_timeout_is_not_a_project_failure(self):
        check = Check("sleep", (sys.executable, "-c", "import time; time.sleep(20)"), 1)
        result = execute(self.root, check)
        self.assertEqual(result["status"], "timeout")
        self.assertLess(result["duration_seconds"], 8)

    def test_launch_failure_is_distinct(self):
        result = execute(self.root, Check("missing", ("definitely-not-a-real-executable-123",), 1))
        self.assertEqual(result["status"], "launch_error")
        self.assertIsNone(result["exit_code"])

    def test_secrets_not_inherited_or_stored(self):
        self.write(
            "app.py",
            "import os\nprint(os.getenv('SYNTHETIC_API_SECRET', 'not inherited'))\n"
            "print('api_key=' + 'synthetic-value')\n",
        )
        with patch.dict(os.environ, {"SYNTHETIC_API_SECRET": "secret-canary"}):
            service = EvidenceService(self.root, True)
            result = service.run_checks(["tests"])
        stored = service.store.get(result["run_id"])
        self.assertNotIn("secret-canary", json.dumps(stored))
        self.assertNotIn("synthetic-value", json.dumps(stored))
        self.assertIn("not inherited", stored["results"][0]["log"])

    def test_log_output_is_bounded_and_tail_preserved(self):
        check = Check(
            "verbose", (sys.executable, "-c", "print('x'*1200000); print('TAIL-MARKER')"), 10
        )
        result = execute(self.root, check)
        self.assertTrue(result["log_truncated"])
        self.assertLessEqual(len(result["log"]), 1_000_000)
        self.assertIn("TAIL-MARKER", result["log"])

    def test_summary_deduplicates_and_caps_diagnostics(self):
        log = "\n".join(["ERROR same"] * 100 + [f"ERROR distinct {i}" for i in range(30)])
        result = summarize(log)
        self.assertEqual(len(result["diagnostics"]), 12)
        self.assertEqual(result["unique_diagnostic_count"], 31)
        self.assertEqual(result["diagnostics_omitted"], 19)

    def test_success_not_inferred_from_output(self):
        check = Check("printed", (sys.executable, "-c", "print('FAILED fake text')"), 10)
        self.assertEqual(execute(self.root, check)["status"], "passed")

    def test_environment_change_invalidates_evidence(self):
        service = EvidenceService(self.root, True)
        result = service.run_checks(["tests"])
        with patch("code_evidence.service.environment_digest", return_value="different"):
            self.assertEqual(service.get_run_summary(result["run_id"])["freshness"], "stale")

    def test_ignored_files_do_not_pollute_source_freshness(self):
        before = snapshot(self.root)
        self.write(".code-evidence/log.txt", "runtime")
        self.write(".env", "API_KEY=private")
        self.write(".venv/generated.py", "runtime")
        self.assertEqual(snapshot(self.root)["digest"], before["digest"])

    def test_incomplete_snapshot_never_fresh(self):
        self.write("large.bin", "x" * 2_000_001)
        result = EvidenceService(self.root, True).run_checks(["tests"])
        self.assertEqual(result["freshness"], "unknown")

    def test_active_lease_blocks_parallel_run(self):
        service = EvidenceService(self.root, True)
        service.store.begin({"run_id": "synthetic", "results": []}, 60)
        with self.assertRaisesRegex(ValueError, "active"):
            service.run_checks(["tests"])

    def test_evidence_bounds(self):
        service = EvidenceService(self.root, True)
        result = service.run_checks(["tests"])
        for start, count in ((0, 1), (1, 101)):
            with self.assertRaises(ValueError):
                service.read_evidence(result["run_id"], "tests", start, count)

    def test_bad_policy_rejected(self):
        self.policy(["{python}", "app.py"], timeout=301)
        with self.assertRaises(ValueError):
            load_checks(self.root)

    def test_cli_requires_explicit_execution(self):
        args = [sys.executable, "-m", "code_evidence.cli", "--project", str(self.root)]
        result = subprocess.run([*args, "run", "tests"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        result = subprocess.run(
            [*args, "run", "tests", "--execute"], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["results"][0]["status"], "passed")

    def test_compare_runs_reports_resolved_failure(self):
        self.write("app.py", "raise ValueError('synthetic failure')\n")
        service = EvidenceService(self.root, True)
        failed = service.run_checks(["tests"])
        self.write("app.py", "print('fixed')\n")
        passed = service.run_checks(["tests"])
        result = service.get_run_summary(passed["run_id"], failed["run_id"])
        self.assertEqual(result["comparison"][0]["previous_status"], "failed")
        self.assertEqual(result["comparison"][0]["current_status"], "passed")
        self.assertTrue(result["comparison"][0]["resolved_diagnostics"])


if __name__ == "__main__":
    unittest.main()
