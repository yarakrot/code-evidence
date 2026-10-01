"""STDIO MCP adapter. Only protocol traffic is written to stdout."""

from .service import EvidenceService


def create_server(service: EvidenceService):
    try:
        from mcp.server import MCPServer
        from mcp.server.mcpserver.exceptions import ToolError
        from mcp.types import ToolAnnotations
    except ImportError as error:
        raise ValueError("Install code-evidence[mcp] to enable the MCP server.") from error
    server = MCPServer("Code Evidence")

    @server.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
    def build_context(task: str, budget_bytes: int = 12_000) -> dict:
        """Select bounded redacted Python fragments with line evidence and heuristic reasons."""
        try:
            return service.build_context(task, budget_bytes)
        except ValueError as error:
            raise ToolError(str(error)) from error

    @server.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
    def inspect_change() -> dict:
        """Read source changes and configured checks; never runs project commands."""
        return service.inspect_change()

    @server.tool(
        annotations=ToolAnnotations(
            read_only_hint=False, destructive_hint=True, open_world_hint=True
        )
    )
    def run_checks(checks: list[str]) -> dict:
        """Execute selected configured check names only when startup policy allows it."""
        try:
            return service.run_checks(checks)
        except ValueError as error:
            raise ToolError(str(error)) from error

    @server.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
    def get_run_summary(run_id: str | None = None, compare_to: str | None = None) -> dict:
        """Read compact diagnostics and current evidence freshness for a stored run."""
        try:
            return service.get_run_summary(run_id, compare_to)
        except ValueError as error:
            raise ToolError(str(error)) from error

    @server.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
    def read_evidence(run_id: str, check: str, start_line: int = 1, max_lines: int = 40) -> dict:
        """Read a bounded redacted log fragment; locations refer to the stored log."""
        try:
            return service.read_evidence(run_id, check, start_line, max_lines)
        except ValueError as error:
            raise ToolError(str(error)) from error

    return server


def serve(service: EvidenceService):
    create_server(service).run(transport="stdio")
