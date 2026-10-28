import json
import os
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

class InstallationTests(unittest.TestCase):
    def test_install_paths_and_preserve_existing_config(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            codex=Path(tmp)
            config=codex/'config.toml'
            config.write_text('model = "existing-model"\n')
            env={**os.environ,'CODEX_HOME':str(codex)}
            command=[sys.executable,str(root/'scripts/install-local-integration.py')]
            subprocess.run(command+['--dry-run'],env=env,capture_output=True,check=True)
            self.assertFalse((codex/'skills').exists())
            result=subprocess.run(command,env=env,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))
            parsed=tomllib.loads(config.read_text(encoding="utf-8"))
            self.assertEqual(parsed['model'],'existing-model')
            self.assertEqual(parsed['mcp_servers']['career_discovery']['command'],str(Path(sys.executable).absolute()))
            self.assertEqual(parsed['mcp_servers']['career_discovery']['args'][-1],str(root))
            local=json.loads((codex/'skills/career-discovery/references/local-installation.json').read_text(encoding="utf-8"))
            self.assertEqual(local['project_root'],str(root))
            before=config.read_bytes()
            result=subprocess.run(command,env=env,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))
            self.assertEqual(config.read_bytes(),before)
