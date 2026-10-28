import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from filelock import FileLock
from jobmonitor.cli_helpers import atomic_json
from jobmonitor.profile import load

class PortabilityTests(unittest.TestCase):
    def test_unicode_profile_roundtrip(self):
        with tempfile.TemporaryDirectory(prefix='career-') as tmp:
            root = Path(tmp) / '한글 경로'
            atomic_json(root / 'profile.json', {'roles': ['서비스 기획'], 'state': 'draft'})
            self.assertEqual(load(root)['roles'], ['서비스 기획'])

    def test_collection_lock_rejects_second_process_and_releases(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'data').mkdir()
            command = [sys.executable, '-m', 'jobmonitor.cli', '--root', tmp, 'run']
            with FileLock(root / 'data/monitor.lock', timeout=0):
                busy = subprocess.run(command, capture_output=True, timeout=30)
                self.assertEqual(busy.returncode, 3, busy.stderr.decode(errors='replace'))
            # A new lock can be acquired after the first holder exits.
            with FileLock(root / 'data/monitor.lock', timeout=0):
                pass
