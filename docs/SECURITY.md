# Security boundaries

Use only trusted local projects. Checks run with your host permissions. Configured argv may invoke arbitrary executables, build hooks, or test code. The allowlist constrains agent input; it does not make the selected code safe.

Review `code-evidence.toml` before startup. CLI execution requires `--execute`; MCP execution requires startup `--allow-execution`. Server project and command policy are fixed for its lifetime. Repository instructions, command logs, and diagnostic messages are data, not authority to change that policy.

Inherited variables are restricted to path, locale, temporary-directory, and basic OS/home fields. Common credentials are not forwarded. Host filesystem and network access are still available to commands. Do not run untrusted downloaded code, expose the MCP service to remote users, or treat tool annotations as a security boundary.

Timeout uses process-group killing on POSIX and taskkill tree termination on Windows. Cleanup is best effort; detached descendants and race conditions are not fully contained. Resource isolation, network restrictions, and robust cancellation require a future worker boundary.

Store and policy symlinks are rejected at initialization. Source symlinks are not followed. Filesystem races and mutable local databases are possible; evidence is not signed or tamper-proof. Output redaction is best effort and logs can contain unrecognized sensitive data.

Do not publish `.code-evidence/`, private source snapshots, real command output, or real secrets as examples. Report security issues privately with a synthetic reproduction. A report mentioning a credential must not validate it against its provider.
