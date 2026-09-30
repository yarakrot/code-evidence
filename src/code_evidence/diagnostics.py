"""Conservative log extraction; fallback retains the tail instead of guessing."""

import re

DIAGNOSTIC = re.compile(
    r"(?:\b(?:FAILED|FAIL|ERROR|Error|Exception|AssertionError|ImportError|"
    r"ModuleNotFoundError|SyntaxError|TypeError|ValueError)\b|"
    r"\berror TS\d+\b|:\d+:\d+: [A-Z]\d{3}\b|^E\s|^Found \d+ error|^Ran \d+ test)",
)


def summarize(log: str, limit: int = 12) -> dict:
    lines = log.splitlines()
    seen = set()
    items = []
    for number, line in enumerate(lines, 1):
        if not DIAGNOSTIC.search(line):
            continue
        normalized = re.sub(r"\s+", " ", line.strip())
        if normalized in seen:
            continue
        seen.add(normalized)
        if len(items) < limit:
            items.append({"line": number, "text": normalized[:500]})
    return {
        "diagnostics": items,
        "unique_diagnostic_count": len(seen),
        "diagnostics_omitted": max(0, len(seen) - limit),
        "tail": "\n".join(lines[-8:])[:2000] if not items else "",
        "stored_log_lines": len(lines),
        "stored_log_characters": len(log),
    }
