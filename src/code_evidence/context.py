"""Fresh, bounded Python context selection. Lexical heuristics, not semantic search."""

import ast
import hashlib
import json
import re
from pathlib import Path

from .redaction import redact, sanitize
from .snapshot import snapshot

MAX_RESPONSE_BYTES = 60_000
MAX_PYTHON_FILES = 300
MAX_SOURCE_BYTES = 1_000_000
MAX_SYMBOLS = 2500
STOPWORDS = {
    "fix",
    "the",
    "a",
    "an",
    "and",
    "for",
    "in",
    "of",
    "to",
    "code",
    "исправь",
    "добавь",
    "код",
    "для",
    "и",
    "в",
    "на",
    "это",
    "ошибку",
}


def terms(text: str) -> set[str]:
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    return {
        t.lower() for t in re.findall(r"[^\W_]+", text) if len(t) > 1 and t.lower() not in STOPWORDS
    }


def encoded_size(value: dict) -> int:
    return len(json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode("utf-8"))


def extract(path: str, source: str, digest: str) -> list[dict]:
    tree = ast.parse(source)
    lines = source.splitlines()
    symbols = []

    def visit(node, prefix=""):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = prefix + child.name
                start = min([child.lineno] + [d.lineno for d in child.decorator_list])
                end = child.end_lineno or child.lineno
                text = "\n".join(lines[start - 1 : end])
                calls = {
                    c.func.id if isinstance(c.func, ast.Name) else c.func.attr
                    for c in ast.walk(child)
                    if isinstance(c, ast.Call) and isinstance(c.func, (ast.Name, ast.Attribute))
                }
                symbols.append(
                    {
                        "path": path,
                        "symbol": name,
                        "start_line": start,
                        "end_line": end,
                        "file_digest": digest,
                        "text": text,
                        "calls": calls,
                        "name": child.name,
                    }
                )
                visit(child, name + ".")
            else:
                visit(child, prefix)

    visit(tree)
    if not symbols and source.strip():
        symbols.append(
            {
                "path": path,
                "symbol": "<module>",
                "start_line": 1,
                "end_line": len(lines),
                "file_digest": digest,
                "text": source,
                "calls": set(),
                "name": "<module>",
            }
        )
    return symbols


def build_context(root: Path, task: str, budget_bytes: int = 12_000) -> dict:
    root = root.resolve()
    if not isinstance(task, str) or not 1 <= len(task.strip()) <= 2000:
        raise ValueError("Describe a task in between 1 and 2000 characters.")
    if type(budget_bytes) is not int or not 2000 <= budget_bytes <= MAX_RESPONSE_BYTES:
        raise ValueError("Context budget must be between 2000 and 60000 serialized bytes.")
    query = terms(task)
    if not query:
        raise ValueError("Include a meaningful symbol, path, or task keyword.")
    inventory = snapshot(root)
    symbols = []
    skipped = []
    paths = sorted(p for p in inventory["files"] if p.endswith(".py"))
    for path in paths[:MAX_PYTHON_FILES]:
        file = root / path
        try:
            if file.is_symlink() or not file.resolve().is_relative_to(root):
                skipped.append(path)
                continue
            with file.open("rb") as stream:
                raw = stream.read(MAX_SOURCE_BYTES + 1)
            if len(raw) > MAX_SOURCE_BYTES:
                skipped.append(path)
                continue
            digest = hashlib.sha256(raw).hexdigest()
            if digest != inventory["files"][path]:
                skipped.append(path)
                continue
            found = extract(path, raw.decode("utf-8-sig"), digest)
            room = MAX_SYMBOLS - len(symbols)
            symbols.extend(found[:room])
            if len(found) > room or len(symbols) >= MAX_SYMBOLS:
                skipped.append("symbol-count limit")
                break
        except (OSError, UnicodeError, SyntaxError, RecursionError):
            skipped.append(path)
    for item in symbols:
        name_hits = query & terms(item["symbol"])
        path_hits = query & terms(item["path"])
        body_hits = query & terms(item["text"])
        item["score"] = 8 * len(name_hits) + 3 * len(path_hits) + len(body_hits)
        item["reasons"] = []
        if name_hits:
            item["reasons"].append("Symbol-name keyword match.")
        if path_hits:
            item["reasons"].append("File-path keyword match.")
        if body_hits and not name_hits:
            item["reasons"].append("Source-text keyword match.")
    seeds = sorted(symbols, key=lambda s: (-s["score"], s["path"], s["start_line"]))[:3]
    seeds = [s for s in seeds if s["score"] > 0]
    for item in symbols:
        for seed in seeds:
            if item is seed:
                continue
            if item["name"] in seed["calls"]:
                item["score"] += 5 if item["path"] == seed["path"] else 2
                item["reasons"].append("Heuristic callee-name match; resolution is unverified.")
            if seed["name"] in item["calls"]:
                item["score"] += 4 if item["path"] == seed["path"] else 1
                item["reasons"].append("Heuristic caller-name match; resolution is unverified.")
    ranked = sorted(
        (s for s in symbols if s["score"] > 0),
        key=lambda s: (-s["score"], s["path"], s["start_line"]),
    )
    result = {
        "schema_version": "1.0",
        "project": root.name,
        "selection": "lexical_python_ast",
        "budget_bytes": budget_bytes,
        "serialized_bytes": 0,
        "snapshot_digest": inventory["digest"],
        "fragments": [],
        "coverage": {
            "python_files_seen": len(paths),
            "symbols_indexed": len(symbols),
            "matching_symbols": len(ranked),
            "omitted_matches": len(ranked),
            "index_complete": inventory["complete"]
            and not skipped
            and len(paths) <= MAX_PYTHON_FILES,
            "skipped_count": len(skipped) + len(inventory["omissions"]),
        },
        "limits": [
            "Lexical matching; no embeddings, semantic understanding, or execution.",
            "Call-name links are heuristic; dynamic imports and dispatch are unverified.",
            "Fragments are redacted; review before sharing. No token savings claimed.",
        ],
    }
    selected = []
    for item in ranked:
        if any(
            old["path"] == item["path"]
            and old["start_line"] <= item["end_line"]
            and item["start_line"] <= old["end_line"]
            for old in selected
        ):
            continue
        fragment = {
            key: item[key] for key in ("path", "symbol", "start_line", "end_line", "file_digest")
        }
        fragment["reasons"] = list(dict.fromkeys(item["reasons"]))
        fragment["text"] = redact(item["text"], str(root))
        fragment["symbol_end_line"] = item["end_line"]
        fragment["fragment_truncated"] = False
        result["fragments"].append(fragment)
        if encoded_size(sanitize(result, str(root))) + 32 > budget_bytes:
            if len(result["fragments"]) > 1:
                result["fragments"].pop()
                continue
            lines = item["text"].splitlines()
            low, high = 0, len(lines)
            fragment["fragment_truncated"] = True
            while low < high:
                middle = (low + high + 1) // 2
                fragment["text"] = redact("\n".join(lines[:middle]), str(root))
                fragment["end_line"] = item["start_line"] + middle - 1
                if encoded_size(sanitize(result, str(root))) + 32 <= budget_bytes:
                    low = middle
                else:
                    high = middle - 1
            if low == 0:
                result["fragments"].pop()
                continue
            fragment["text"] = redact("\n".join(lines[:low]), str(root))
            fragment["end_line"] = item["start_line"] + low - 1
        selected.append({**item, "end_line": fragment["end_line"]})
    result["coverage"]["omitted_matches"] = len(ranked) - len(selected)
    result = sanitize(result, str(root))
    for _ in range(3):
        result["serialized_bytes"] = encoded_size(result)
    return result
