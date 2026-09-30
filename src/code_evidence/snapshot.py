"""Source freshness, not a reproducible-build certificate or result cache."""

import hashlib
import json
import os
from pathlib import Path

IGNORED = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".code-evidence",
    ".ruff_cache",
    ".pytest_cache",
    "build",
    "dist",
    "uploads",
    "outputs",
    "cache",
    "tmp",
}
MAX_FILES = 5000
MAX_FILE_BYTES = 2_000_000
MAX_TOTAL_BYTES = 30_000_000


def snapshot(root: Path) -> dict:
    files = {}
    omissions = []
    total = 0
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(
            d
            for d in dirs
            if d not in IGNORED
            and not d.endswith((".egg-info", ".dist-info"))
            and not (Path(directory) / d).is_symlink()
        )
        for name in sorted(names):
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            if name.startswith(".env") or path.suffix.lower() in {".pem", ".key", ".p12"}:
                continue
            if path.is_symlink():
                omissions.append(relative)
                continue
            if len(files) >= MAX_FILES:
                omissions.append("file-count limit")
                return finish(files, omissions)
            try:
                with path.open("rb") as stream:
                    content = stream.read(MAX_FILE_BYTES + 1)
                if len(content) > MAX_FILE_BYTES:
                    omissions.append(relative)
                    continue
                if total + len(content) > MAX_TOTAL_BYTES:
                    omissions.append("total-byte limit")
                    return finish(files, omissions)
                total += len(content)
                files[relative] = hashlib.sha256(content).hexdigest()
            except OSError:
                omissions.append(relative)
    return finish(files, omissions)


def finish(files: dict, omissions: list) -> dict:
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    return {"digest": digest, "files": files, "complete": not omissions, "omissions": omissions}


def changes(before: dict, after: dict) -> dict:
    old, new = before["files"], after["files"]
    result = {
        "added": sorted(new.keys() - old.keys()),
        "removed": sorted(old.keys() - new.keys()),
        "modified": sorted(name for name in new.keys() & old.keys() if new[name] != old[name]),
    }
    counts = {key: len(value) for key, value in result.items()}
    result = {key: value[:50] for key, value in result.items()}
    result["counts"] = counts
    result["truncated"] = any(count > 50 for count in counts.values())
    return result
