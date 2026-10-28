import asyncio
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HAS_MCP=importlib.util.find_spec("mcp") is not None

@unittest.skipUnless(HAS_MCP,"optional MCP SDK not installed")
class MCPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
    def tearDown(self):
        self.temp.cleanup()
    def test_status_does_not_create_database_or_leak_keys(self):
        from jobmonitor.mcp_server import status
        with patch.dict(os.environ,{"NAVER_CLIENT_SECRET":"test-value-never-output"}):
            value=status(self.root)
        self.assertNotIn("test-value-never-output",json.dumps(value))
        self.assertTrue(value["credentials_present"]["NAVER_CLIENT_SECRET"])
        self.assertFalse((self.root/"data").exists())
    def test_missing_report(self):
        from jobmonitor.mcp_server import summary
        self.assertFalse(summary(self.root)["available"])
    def test_stored_jobs_bounded_and_no_full_body(self):
        from jobmonitor.mcp_server import stored_jobs
        from jobmonitor.core import Store,Job
        (self.root/"data").mkdir()
        store=Store(self.root/"data/jobs.sqlite")
        try:
            store.upsert(Job("company","x","https://example.com/job","물류 신입",text="PRIVATE_FULL_BODY Excel 물류 학력무관 연구"))
        finally: store.close()
        result=stored_jobs(self.root,"물류",0,1)
        self.assertEqual(len(result["jobs"]),1)
        self.assertNotIn("PRIVATE_FULL_BODY",json.dumps(result))
        self.assertTrue(result["untrusted_source_content"])
        with self.assertRaises(ValueError): stored_jobs(self.root,limit=999)
    def test_collection_captures_stdout(self):
        from jobmonitor.mcp_server import collect
        with patch("jobmonitor.mcp_server.subprocess.run") as call:
            call.return_value.returncode=2
            self.assertEqual(collect(self.root)["status"],"partial")
            self.assertTrue(call.call_args.kwargs["capture_output"])
            self.assertIn("run",call.call_args.args[0])
    def test_discovery_never_searches(self):
        from jobmonitor.mcp_server import open_discovery
        with patch("jobmonitor.mcp_server.socket.socket") as sock, patch("jobmonitor.mcp_server.subprocess.Popen") as spawn:
            sock.return_value.__enter__.return_value.connect_ex.return_value=1
            value=open_discovery(self.root)
            self.assertIn("127.0.0.1",value["url"])
            self.assertNotIn("items",value)
            self.assertIn("discover",spawn.call_args.args[0])
    def test_existing_port_no_process_spawn(self):
        from jobmonitor.mcp_server import open_discovery
        with patch("jobmonitor.mcp_server.socket.socket") as sock, patch("jobmonitor.mcp_server.subprocess.Popen") as spawn:
            sock.return_value.__enter__.return_value.connect_ex.return_value=0
            self.assertEqual(open_discovery(self.root)["status"],"port_in_use")
            spawn.assert_not_called()

@unittest.skipUnless(HAS_MCP,"optional MCP SDK not installed")
class StdioTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_mcp_handshake_list_and_call(self):
        import sys
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        project=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            params=StdioServerParameters(command=sys.executable,
                args=[str(project/"scripts/start-mcp.py"),"--root",tmp],cwd=tmp)
            async with asyncio.timeout(20):
                async with stdio_client(params) as (read,write):
                    async with ClientSession(read,write) as session:
                        await session.initialize()
                        listed=await session.list_tools()
                        names={tool.name for tool in listed.tools}
                        self.assertEqual(names,{"get_status","read_daily_summary","list_jobs","run_collection","open_naver_discovery","get_google_search_links","get_search_profile","save_search_profile","build_search_plan","get_saramin_search_links"})
                        self.assertNotIn("search_naver", names)
                        result=await session.call_tool("get_status",{})
                        self.assertFalse(result.isError)
                        self.assertEqual(result.structuredContent["job_count"],0)
                        self.assertEqual(result.structuredContent["timezone"],"Asia/Seoul")
                        draft=await session.call_tool("build_search_plan",{})
                        self.assertFalse(draft.structuredContent['ready'])
                        saved=await session.call_tool("save_search_profile",{"profile":{"state":"confirmed","roles":["제품기획"],"industries":["게임"]}})
                        self.assertFalse(saved.isError)
                        plan=await session.call_tool("build_search_plan",{})
                        self.assertIn('게임 제품기획 채용',plan.structuredContent['queries'])
                        empty=await session.call_tool("list_jobs",{"limit":2})
                        self.assertFalse(empty.isError)
                        self.assertEqual(empty.structuredContent["jobs"],[])
