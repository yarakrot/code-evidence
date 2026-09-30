# Code Evidence

**Give coding agents compact failure reports and evidence tied to the code they checked.**

Code Evidence combines Failure Lens and Proof of Change in a local Python core, CLI, and STDIO MCP server. It needs no LLM or paid API. Context selection and sandbox execution are future extensions, not shipped features.

## What Works Today

- Execute explicitly configured check names, with no arbitrary command argument exposed through MCP.
- Store run history and redacted logs in local SQLite, retaining the latest 50 runs.
- Extract and deduplicate diagnostic lines from Python/unittest/pytest, Ruff-style, and TypeScript-style output; retain a tail when no pattern matches.
- Read log fragments on demand instead of returning full logs to the model.
- Compare sampled diagnostics between attempts, including newly observed and absent messages.
- Track included file content, configured check policy, and the server's Python/environment fingerprint.
- Mark results `fresh`, `stale`, or `unknown`; never reuse a cached result as a new execution.
- Distinguish nonzero exits, launch errors, timeouts, and capture errors.

**This is trusted local execution, not a sandbox.** Configure it only for projects and check commands you trust. A test or build hook can run arbitrary code with your user permissions, access files, contact the network, or alter its own logs.

## Install

Python 3.12+ is required. Install into the Python environment you want the checks to use:

```powershell
git clone https://github.com/yarakrot/code-evidence.git
cd code-evidence
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,mcp]"
```

The core has no runtime dependencies. The optional `mcp` extra uses the official MCP Python SDK; the `dev` extra installs Ruff.

## CLI Workflow

```powershell
.\.venv\Scripts\code-evidence.exe --project . inspect
.\.venv\Scripts\code-evidence.exe --project . run tests lint format --execute
.\.venv\Scripts\code-evidence.exe --project . summary
```

`inspect` and `summary` do not execute project checks. `run` requires `--execute`. Checks run sequentially with stdin disabled, `shell=False`, a filtered environment, and a configured timeout. CLI returns 1 if a selected check fails, and 2 for invalid input/policy.

Compare attempts or read the stored log:

```powershell
code-evidence --project . summary --run-id NEW_RUN_ID --compare-to OLD_RUN_ID
code-evidence --project . evidence RUN_ID tests --start-line 1 --max-lines 40
```

Output is JSON. `run_id` comes from the returned receipt. Do not copy the placeholder IDs literally.

## Configure Another Project

Create `code-evidence.toml` in the trusted project's root:

```toml
schema_version = 1

[checks.tests]
argv = ["{python}", "-m", "unittest", "discover", "-s", "tests", "-v"]
timeout_seconds = 60

[checks.lint]
argv = ["{python}", "-m", "ruff", "check", "."]
timeout_seconds = 60
```

`{python}` resolves to the interpreter running Code Evidence. Install the project's test dependencies in that same environment or explicitly configure a trusted executable. The policy is loaded once at server startup; an agent cannot replace it with a new argv through a tool call. Review edited policy before restarting the server. Commands are not automatically generated from a README.

## MCP Tools

| Tool | Behavior |
| --- | --- |
| `inspect_change` | Show configured checks and bounded changes since the last run |
| `run_checks` | Run selected configured check names if enabled at startup |
| `get_run_summary` | Read diagnostics, freshness, and optional comparison |
| `read_evidence` | Read a bounded fragment of a stored redacted log |

Launch with `code-evidence --project /path/to/project serve`. This defaults to read-only tool behavior: `run_checks` returns a policy error. To permit configured commands, add `--allow-execution` when starting the server.

Example configuration for an MCP client that supports `mcpServers`:

```json
{
  "mcpServers": {
    "code-evidence": {
      "command": "C:/path/to/project/.venv/Scripts/python.exe",
      "args": [
        "-m", "code_evidence.cli",
        "--project", "C:/path/to/project",
        "serve"
      ]
    }
  }
}
```

Replace both example paths. This configuration is read-only; enabling execution is an explicit startup decision. Different clients use different configuration formats. The server does not modify your client settings or register itself automatically. Protocol output uses stdout; diagnostic logging uses stderr.

## Evidence Semantics

- `fresh`: the included source, startup policy, and server environment still match the run, and included source did not change during it.
- `stale`: one of those observed fingerprints changed.
- `unknown`: inventory was incomplete or the run did not finish normally.

Freshness is **not** proof of correctness, a reproducible build, or verification of external services, ignored secrets, separate tool environments, OS binaries, or transient file changes restored before the final snapshot. Success comes from process exit status, not a reassuring line in stdout. A process can exit 0 without adequate tests.

Source inventory excludes Git metadata, virtual environments, runtime folders, `.env` files, and private-key extensions. Files are bounded to 2 MB each, 30 MB total, and 5000 included entries. Logs retain at most the last 1 MB per check and report truncation. Diagnostic summaries retain up to 12 distinct messages; run comparisons operate on those sampled messages. Evidence fragments are capped at 100 lines and 16,000 characters. Changed-file lists are capped at 50 entries per category with full counts.

SQLite and logs remain in `.code-evidence/`, excluded from Git. Output redaction is best effort: review exports before sharing. The tool filters inherited environment variables but **does not prevent trusted commands from reading your files or retrieving credentials themselves**.

## Development

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
```

CI tests Windows/Linux on Python 3.12 and 3.13, including a real STDIO MCP discovery and tool-call session. Tests use synthetic trusted commands, never private repository snapshots or real keys.

## Next Steps

See [architecture](docs/ARCHITECTURE.md), [security boundaries](docs/SECURITY.md), and [roadmap](docs/ROADMAP.md). Planned: AST-based Context Budget, richer diagnostic adapters, README Reality integration, isolated execution, and measured agent benchmarks. No token-saving percentage is claimed by this release.

## License

MIT. See [LICENSE](LICENSE).
