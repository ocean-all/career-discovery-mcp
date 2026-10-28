"""Absolute-path entrypoint for MCP clients with any working directory."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from jobmonitor.mcp_server import main
if __name__ == "__main__":
    main()
