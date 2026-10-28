"""Small shared atomic writer to avoid profile/CLI import cycles."""
import json
import os
import tempfile
from pathlib import Path

def atomic_json(path,value):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=path.parent,delete=False) as out:
        json.dump(value,out,ensure_ascii=False,indent=2)
        temp=Path(out.name)
    temp.chmod(0o600)
    temp.replace(path)
