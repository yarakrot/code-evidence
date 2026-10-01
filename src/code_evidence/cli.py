"""CLI adapter; execution opt-in is explicit and never implied by inspection."""

import argparse
import json
from pathlib import Path

from .service import EvidenceService


def main() -> int:
    parser = argparse.ArgumentParser(description="Local verification evidence for coding agents.")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    subs = parser.add_subparsers(dest="command", required=True)
    subs.add_parser("inspect")
    context = subs.add_parser("context")
    context.add_argument("task")
    context.add_argument("--budget-bytes", type=int, default=12_000)
    run = subs.add_parser("run")
    run.add_argument("checks", nargs="+")
    run.add_argument("--execute", action="store_true", help="Allow trusted-host execution")
    summary = subs.add_parser("summary")
    summary.add_argument("--run-id")
    summary.add_argument("--compare-to")
    evidence = subs.add_parser("evidence")
    evidence.add_argument("run_id")
    evidence.add_argument("check")
    evidence.add_argument("--start-line", type=int, default=1)
    evidence.add_argument("--max-lines", type=int, default=40)
    serve = subs.add_parser("serve")
    serve.add_argument("--allow-execution", action="store_true")
    args = parser.parse_args()
    try:
        service = EvidenceService(
            args.project,
            bool(getattr(args, "execute", False) or getattr(args, "allow_execution", False)),
        )
        if args.command == "serve":
            from .mcp_server import serve

            serve(service)
            return 0
        if args.command == "inspect":
            result = service.inspect_change()
        elif args.command == "context":
            result = service.build_context(args.task, args.budget_bytes)
        elif args.command == "run":
            result = service.run_checks(args.checks)
        elif args.command == "summary":
            result = service.get_run_summary(args.run_id, args.compare_to)
        else:
            result = service.read_evidence(args.run_id, args.check, args.start_line, args.max_lines)
        print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
        if args.command == "run" and any(r["status"] != "passed" for r in result["results"]):
            return 1
        return 0
    except (OSError, ValueError) as error:
        parser.exit(2, f"Code Evidence: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
