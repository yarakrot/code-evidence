"""Best-effort output scrubbing. Stored logs are redacted, not raw."""

import re

PATTERNS = [
    re.compile(
        r"\b(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,})\b"
    ),
    re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{30,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\b"),
    re.compile(r"(?im)((?:api[_-]?key|password|secret|access[_-]?token)\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
]


def redact(value: str, root: str = "") -> str:
    if root:
        for spelling in {root, root.replace("\\", "/"), root.replace("/", "\\")}:
            value = value.replace(spelling, "<project>")
    for pattern in PATTERNS:
        value = pattern.sub("[REDACTED]", value)
    return value


def sanitize(value, root: str = ""):
    if isinstance(value, str):
        return redact(value, root)
    if isinstance(value, dict):
        return {key: sanitize(item, root) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [sanitize(item, root) for item in value]
    return value
