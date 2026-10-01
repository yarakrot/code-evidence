# Changelog

## 0.2.0 — 2026-10-01

- Added read-only Context Budget through CLI and MCP.
- Python AST fragments include evidence locations, file hashes, and heuristic inclusion reasons.
- Bounded compact JSON includes metadata; coverage and omissions remain explicit.
- Source is reread on each request; known secrets are redacted before output.
- Added eight context regressions and extended real MCP protocol coverage.

## 0.1.0 — 2026-09-30

- Local CLI and STDIO MCP with four project-bound tools.
- Startup-frozen check policy and explicit execution opt-in.
- SQLite run receipts with included-source/environment/policy freshness.
- Bounded redacted logs, conservative diagnostic extraction, and attempt comparison.
- Timeout handling, sequential execution, and active-run lease.
- Synthetic core regressions and a real STDIO MCP integration test.

Trusted-host execution only. Context Budget, isolated workers, and HTTP/UI adapters are planned.
