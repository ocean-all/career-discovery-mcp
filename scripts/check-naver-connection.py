"""Probe authentication only; discard all search content; print no credentials."""
import json
import os
import sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from jobmonitor.cli import load_env, atomic_write
from jobmonitor.core import Store, now
from jobmonitor.providers import Naver
from jobmonitor.http import HTTP, FetchError

load_env(root/".env")
(root/"data").mkdir(exist_ok=True)
store=Store(root/"data/jobs.sqlite")
checks=[]
try:
    for mode in ("hub","legacy"):
        os.environ["NAVER_MODE"]=mode
        try:
            result=Naver(HTTP(store)).search("물류 신입 채용",display=1)
            success="items" in result
            del result
            checks.append({"mode":mode,"authenticated":success})
            if success:
                p=root/".env"
                lines=[line for line in p.read_text(encoding="utf-8").splitlines() if not line.startswith("NAVER_MODE=")]
                atomic_write(p,"\n".join(lines+["NAVER_MODE="+mode])+"\n")
                p.chmod(0o600)
                break
        except (FetchError,RuntimeError) as exc:
            checks.append({"mode":mode,"authenticated":False,"error":str(exc)})
    status={"checked_at":now().isoformat(),"checks":checks}
    atomic_write(root/"data/naver-connection.json",json.dumps(status,ensure_ascii=False,indent=2))
    print(json.dumps(status,ensure_ascii=False))
finally:
    store.close()
