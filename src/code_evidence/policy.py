"""Configuration is loaded once; agents cannot submit arbitrary execution argv."""

import hashlib
import json
import re
import sys
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Check:
    name: str
    argv: tuple[str, ...]
    timeout_seconds: int


def load_checks(root: Path, python: str = sys.executable) -> dict[str, Check]:
    path = root / "code-evidence.toml"
    if path.is_symlink():
        raise ValueError("The check policy must not be a symlink.")
    if path.stat().st_size > 100_000:
        raise ValueError("The check policy is too large.")
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("Unsupported check policy schema.")
    checks = {}
    entries = data.get("checks", {})
    if not isinstance(entries, dict) or not 1 <= len(entries) <= 20:
        raise ValueError("Configure between one and twenty checks.")
    for name, entry in entries.items():
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", name) or not isinstance(entry, dict):
            raise ValueError("Use short lowercase check names and TOML tables.")
        argv = entry.get("argv")
        timeout = entry.get("timeout_seconds", 60)
        if not isinstance(argv, list) or not 1 <= len(argv) <= 100:
            raise ValueError(f"Invalid argv for check {name}.")
        if any(not isinstance(arg, str) or "\0" in arg or len(arg) > 4096 for arg in argv):
            raise ValueError(f"Invalid argument for check {name}.")
        if type(timeout) is not int or not 1 <= timeout <= 300:
            raise ValueError(f"Timeout for {name} must be between 1 and 300 seconds.")
        checks[name] = Check(
            name, tuple(python if arg == "{python}" else arg for arg in argv), timeout
        )
    return checks


def policy_digest(checks: dict[str, Check]) -> str:
    value = {name: asdict(check) for name, check in sorted(checks.items())}
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
