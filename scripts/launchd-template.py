"""Generate a reviewable LaunchAgent plist; does not install or start it."""
import plistlib
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
python = root / ".venv/bin/python"
if not python.exists():
    sys.exit("Create .venv first; see README.md")
(root / "data").mkdir(exist_ok=True)
plist = {
    "Label": "local.career-discovery",
    "ProgramArguments": [str(python), "-m", "jobmonitor.cli", "--root", str(root), "schedule"],
    "WorkingDirectory": str(root), "RunAtLoad": True, "KeepAlive": True,
    "StandardOutPath": str(root / "data/scheduler.log"),
    "StandardErrorPath": str(root / "data/scheduler-error.log"),
    "ThrottleInterval": 60,
}
out = root / "scripts/local.career-discovery.plist"
out.write_bytes(plistlib.dumps(plist))
print(out)
