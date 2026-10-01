import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError:
    ClientSession = None


@unittest.skipIf(ClientSession is None, "Install the optional MCP extra to run protocol tests.")
class MCPIntegrationTests(unittest.TestCase):
    def test_stdio_discovery_reading_and_execution_policy(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "code-evidence.toml").write_text(
                "schema_version = 1\n[checks.smoke]\n"
                'argv = ["{python}", "-c", "print(123)"]\ntimeout_seconds = 5\n',
                encoding="utf-8",
            )

            async def scenario(enabled):
                args = ["-m", "code_evidence.cli", "--project", str(root), "serve"]
                if enabled:
                    args.append("--allow-execution")
                params = StdioServerParameters(command=sys.executable, args=args)
                async with stdio_client(params) as (read, write):
                    async with ClientSession(read, write, read_timeout_seconds=20) as client:
                        await client.initialize()
                        tools = await client.list_tools()
                        self.assertEqual(
                            {t.name for t in tools.tools},
                            {
                                "build_context",
                                "inspect_change",
                                "run_checks",
                                "get_run_summary",
                                "read_evidence",
                            },
                        )
                        by_name = {tool.name: tool for tool in tools.tools}
                        self.assertTrue(by_name["inspect_change"].annotations.read_only_hint)
                        self.assertFalse(by_name["run_checks"].annotations.read_only_hint)
                        result = await client.call_tool("inspect_change", {})
                        self.assertFalse(result.is_error)
                        data = result.structured_content or json.loads(result.content[0].text)
                        self.assertEqual(data["execution_enabled"], enabled)
                        context = await client.call_tool("build_context", {"task": "smoke"})
                        self.assertFalse(context.is_error)
                        result = await client.call_tool("run_checks", {"checks": ["smoke"]})
                        self.assertEqual(bool(result.is_error), not enabled)
                        if enabled:
                            data = result.structured_content or json.loads(result.content[0].text)
                            self.assertEqual(data["results"][0]["status"], "passed")
                            fragment = await client.call_tool(
                                "read_evidence",
                                {
                                    "run_id": data["run_id"],
                                    "check": "smoke",
                                },
                            )
                            self.assertFalse(fragment.is_error)

            asyncio.run(scenario(False))
            asyncio.run(scenario(True))
