# Roadmap

## Shipped: Failure Lens + Proof of Change

Local core, check-name policy, explicit host execution, SQLite receipts, bounded redacted logs, diagnostic extraction, attempt comparison, source/environment freshness, CLI, STDIO MCP, and regression tests.

## Shipped: Initial Python Context Budget

Python AST symbols, lexical ranking, heuristic caller/callee names, line spans, inclusion reasons, file hashes, coverage, and a serialized JSON byte budget are implemented. Requests reread source and never execute it. Regression tests cover selection, edits, Unicode budget accounting, redaction, and overlap. Next: precise import resolution, import context, explicit symbol lookup, and measured retrieval quality.

## Diagnostic adapters and honest benchmarks

Add structured pytest/JUnit/Ruff/TypeScript adapters and richer causal links. Benchmark bounded summary size, time to diagnose, correction success, and tool-call count against full-log baselines. Report token usage only when the client exposes real usage; otherwise label character counts or tokenizer estimates.

## README Reality integration

Add a read-only adapter to the separate README Reality package. It supplies installation hypotheses; Code Evidence supplies actual selected-check observations. Preserve that distinction. Avoid copying the other repository's entire source or history.

## Isolated worker

Add a separate Docker/local disposable worker adapter, immutable snapshots, resource limits, no host secret inheritance, and tested cleanup. Host and isolated results have different environment descriptors. Public arbitrary-code execution needs stronger isolation than a shared Docker daemon.

## Optional UI and API Reality

After core contracts stabilize, add a loopback-only HTTP adapter and a review workspace. API contract checking uses explicit endpoints and redacted schema observations. No unrestricted proxy, public listener, or generated external mutation.

## Release gate

Passing Windows/Linux tests, real protocol tests, bounded-output regressions, reviewed history, accurate capability documentation, and known limitations. No automatic claims of saved tokens, safe code, or sufficient test coverage.
