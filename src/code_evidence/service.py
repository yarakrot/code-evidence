"""Core shared by CLI and MCP; project and command policy are startup-bound."""

import hashlib
import importlib.metadata
import json
import platform
import sys
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from . import __version__
from .context import build_context
from .diagnostics import summarize
from .policy import load_checks, policy_digest
from .redaction import sanitize
from .runner import check_environment, execute
from .snapshot import changes, snapshot
from .store import Store


def environment_digest() -> str:
    packages = sorted(
        (d.metadata.get("Name", ""), d.version) for d in importlib.metadata.distributions()
    )
    value = {
        "python": sys.version,
        "platform": platform.platform(),
        "packages": packages,
        "environment": check_environment(),
        "code_evidence": __version__,
    }
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


class EvidenceService:
    def build_context(self, task: str, budget_bytes: int = 12_000) -> dict:
        return build_context(self.root, task, budget_bytes)

    def __init__(self, root: Path, allow_execution: bool = False):
        self.root = root.resolve()
        if not self.root.is_dir():
            raise ValueError("Project directory does not exist.")
        self.checks = load_checks(self.root)
        self.policy_digest = policy_digest(self.checks)
        self.allow_execution = allow_execution
        self.store = Store(self.root / ".code-evidence")

    def inspect_change(self) -> dict:
        current = snapshot(self.root)
        previous = self.store.get()
        result = {
            "schema_version": "1.0",
            "project": self.root.name,
            "execution_enabled": self.allow_execution,
            "checks": [asdict(check) for check in self.checks.values()],
            "snapshot_digest": current["digest"],
            "snapshot_complete": current["complete"],
            "omissions": current["omissions"][:20],
            "baseline_run": None,
            "changed_files": None,
        }
        if previous:
            result["baseline_run"] = previous["run_id"]
            result["changed_files"] = changes(previous["before"], current)
        return sanitize(result, str(self.root))

    def run_checks(self, names: list[str]) -> dict:
        if not self.allow_execution:
            raise ValueError("Execution is disabled. Enable it at startup for a trusted project.")
        if not names or len(names) != len(set(names)) or any(n not in self.checks for n in names):
            raise ValueError("Select unique names from the configured checks.")
        before = snapshot(self.root)
        run = {
            "schema_version": "1.0",
            "run_id": str(uuid.uuid4()),
            "created_at": datetime.now(UTC).isoformat(),
            "project": self.root.name,
            "before": before,
            "environment_digest": environment_digest(),
            "policy_digest": self.policy_digest,
            "results": [],
        }
        lease = sum(self.checks[name].timeout_seconds + 20 for name in names) + 60
        self.store.begin(run, lease)
        try:
            for name in names:
                result = execute(self.root, self.checks[name])
                result["check"] = name
                result["argv"] = list(self.checks[name].argv)
                run["results"].append(sanitize(result, str(self.root)))
            run["after"] = snapshot(self.root)
            run["environment_after"] = environment_digest()
            run["source_consistent"] = before["digest"] == run["after"]["digest"]
            self.store.finish(run, "completed")
        except BaseException:
            self.store.finish(run, "interrupted")
            raise
        return self.get_run_summary(run["run_id"])

    def get_run_summary(self, run_id: str | None = None, compare_to: str | None = None) -> dict:
        run = self.store.get(run_id)
        if not run:
            return {"found": False}
        current = snapshot(self.root)
        if run["state"] != "completed" or not run["before"]["complete"] or not current["complete"]:
            freshness = "unknown"
        elif not run.get("source_consistent") or run["before"]["digest"] != current["digest"]:
            freshness = "stale"
        elif (
            run["environment_digest"] != environment_digest()
            or run["environment_digest"] != run.get("environment_after")
            or run["policy_digest"] != self.policy_digest
        ):
            freshness = "stale"
        else:
            freshness = "fresh"
        summaries = []
        for result in run["results"]:
            compact = {key: value for key, value in result.items() if key != "log"}
            compact.update(summarize(result["log"]))
            summaries.append(compact)
        comparison = None
        if compare_to:
            previous = self.store.get(compare_to)
            if not previous:
                raise ValueError("Comparison run not found.")
            old = {r["check"]: r for r in previous["results"]}
            comparison = []
            for result in run["results"]:
                earlier = old.get(result["check"])
                if not earlier:
                    continue
                old_messages = {d["text"] for d in summarize(earlier["log"])["diagnostics"]}
                new_messages = {d["text"] for d in summarize(result["log"])["diagnostics"]}
                comparison.append(
                    {
                        "check": result["check"],
                        "previous_status": earlier["status"],
                        "current_status": result["status"],
                        "new_diagnostics": sorted(new_messages - old_messages),
                        "resolved_diagnostics": sorted(old_messages - new_messages),
                        "unchanged_diagnostics": sorted(old_messages & new_messages),
                    }
                )
        return sanitize(
            {
                "schema_version": "1.0",
                "found": True,
                "run_id": run["run_id"],
                "state": run["state"],
                "created_at": run["created_at"],
                "freshness": freshness,
                "results": summaries,
                "comparison": comparison,
                "comparison_scope": "Exact-text comparison of sampled diagnostics only.",
                "changed_files": changes(run["before"], current),
                "limits": [
                    "Freshness covers included source, server environment, and policy.",
                    "External files, services, ignored secrets, and other tool environments "
                    "are unverified.",
                    "Logs are redacted and bounded; commands run on the trusted host.",
                ],
            },
            str(self.root),
        )

    def read_evidence(
        self, run_id: str, check: str, start_line: int = 1, max_lines: int = 40
    ) -> dict:
        if start_line < 1 or not 1 <= max_lines <= 100:
            raise ValueError("Use a positive start line and between 1 and 100 lines.")
        run = self.store.get(run_id)
        if not run:
            raise ValueError("Run not found.")
        result = next((r for r in run["results"] if r["check"] == check), None)
        if not result:
            raise ValueError("Check not found in this run.")
        lines = result["log"].splitlines()
        selected = lines[start_line - 1 : start_line - 1 + max_lines]
        text = "\n".join(selected)
        return {
            "run_id": run_id,
            "check": check,
            "start_line": start_line,
            "text": text[:16_000],
            "fragment_truncated": len(text) > 16_000,
            "log_truncated": result["log_truncated"],
            "stored_log_lines": len(lines),
        }
