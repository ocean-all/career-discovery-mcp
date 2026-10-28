# MCP client setup

This is a standard local **stdio MCP server**, independent of Codex. Python 3.11+ on Windows, macOS or Linux is required. Install `.[mcp]` in the project virtual environment first. Each client launches Python as a child process; stdout carries only MCP messages. Credentials stay in the project `.env`.

## Claude Desktop and clients using mcpServers

Merge this entry into the client's MCP configuration, replacing paths with the absolute checkout location. Do not overwrite unrelated servers.

macOS / Linux:

```json
{
  "mcpServers": {
    "career_discovery": {
      "command": "/path/to/project/.venv/bin/python",
      "args": ["/path/to/project/scripts/start-mcp.py", "--root", "/path/to/project"]
    }
  }
}
```

Windows (JSON paths use forward slashes or escaped backslashes):

```json
{
  "mcpServers": {
    "career_discovery": {
      "command": "C:/projects/career-discovery/.venv/Scripts/python.exe",
      "args": ["C:/projects/career-discovery/scripts/start-mcp.py", "--root", "C:/projects/career-discovery"]
    }
  }
}
```

## VS Code

Use **MCP: Add Server → Command (stdio)** with the same executable and arguments, choosing the desired workspace or user scope. With a `.vscode/mcp.json` configuration, use `servers` as the top-level object and add `"type": "stdio"` inside the server entry. Configuration formats depend on the selected agent/harness; see the [official configuration reference](https://code.visualstudio.com/docs/agents/reference/mcp-configuration).

## Optional Codex integration

Run with the project's virtual-environment Python:

```sh
python scripts/install-local-integration.py --dry-run
python scripts/install-local-integration.py
```

This optional helper updates CODEX_HOME or ~/.codex and installs the optional career-discovery skill. It uses the executing Python interpreter, including on Windows. `--update-skill` updates an installation previously managed by this helper. Other clients do not need this installer or the Codex skill metadata.

## Conversation and verification

After reconnecting the client, call `get_status`. The server sends conversation instructions during MCP initialization: reuse existing answers, ask a few adaptive questions, propose adjacent roles with reasons, and confirm accepted scope. The host AI performs the reasoning. If a client does not apply server instructions, add `skills/career-discovery/SKILL.md` as its custom instructions or reference material; automatic skill loading varies by client.

Use `get_search_profile` → conversation → `save_search_profile` → `build_search_plan`. Unaccepted suggestions must stay in `proposed_expansions`. No additional AI key is needed by the server. `run_collection` can take up to 600 seconds; allow at least 660 seconds where a client supports configurable tool timeouts.

The installed `career-discovery-mcp --root <absolute-project-path>` command is also available. A launcher script plus absolute Python path is preferable for desktop clients that do not inherit the terminal PATH.

This release provides local stdio, not a remote HTTP service or shared hosted URL. A cloud-only client without local-process support cannot connect directly. Optional OCR requires Tesseract and language data installed for the relevant OS; PDF image rendering may require Poppler. HWP extraction depends on an available hwp5txt executable. The Naver viewer opens only on the local computer. No MCP setup step enables the scheduler.

References: [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk/tree/v1.30.0), [local MCP server connection](https://modelcontextprotocol.io/docs/develop/connect-local-servers).

On Windows, keep the project in a private user folder with appropriate NTFS permissions. POSIX chmod modes do not set Windows ACLs.
