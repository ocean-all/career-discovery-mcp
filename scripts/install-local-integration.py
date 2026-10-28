"""Install this personal skill and add only this stdio MCP entry to Codex config."""
import argparse
import json
import os
import shutil
import sys
import tempfile
import tomllib
from pathlib import Path

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--dry-run',action='store_true')
parser.add_argument('--update-skill',action='store_true')
args=parser.parse_args()
codex_dir=Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))
source=root/'skills/career-discovery'
destination=codex_dir/'skills/career-discovery'
config=codex_dir/'config.toml'
old=config.read_text(encoding="utf-8") if config.exists() else ''
parsed=tomllib.loads(old)
command=str(Path(sys.executable).absolute())
server_args=[str(root/'scripts/start-mcp.py'),'--root',str(root)]
existing=parsed.get('mcp_servers',{}).get('career_discovery')
if existing and (existing.get('command')!=command or existing.get('args')!=server_args):
    raise SystemExit('Existing career_discovery entry differs; no changes made. Inspect it before replacing.')
files={p.relative_to(source).as_posix():p.read_bytes() for p in source.rglob('*') if p.is_file()}
files['references/local-installation.json']=json.dumps({'managed_by':'korean-career-discovery-mcp','project_root':str(root)},ensure_ascii=False,indent=2).encode('utf-8')
if destination.exists():
    previous={p.relative_to(destination).as_posix():p.read_bytes() for p in destination.rglob('*') if p.is_file()}
    if files!=previous:
        marker=destination/'references/local-installation.json'
        managed=marker.exists() and json.loads(marker.read_text(encoding="utf-8")).get('managed_by')=='korean-career-discovery-mcp'
        if not (args.update_skill and managed):
            raise SystemExit('Existing skill differs; no changes made. Use --update-skill only for a previously managed installation.')
block='\n[mcp_servers.career_discovery]\ncommand = '+json.dumps(command,ensure_ascii=False)+'\nargs = '+json.dumps(server_args,ensure_ascii=False)+'\nstartup_timeout_sec = 20\ntool_timeout_sec = 660\n'
updated=old if existing else old.rstrip()+'\n'+block
tomllib.loads(updated)
if args.dry_run:
    print(json.dumps({'skill_destination':str(destination),'mcp_server':'career_discovery','config':str(config),'credentials_in_config':False},ensure_ascii=False))
else:
    destination.mkdir(parents=True,exist_ok=True)
    for relative,content in files.items():
        path=destination/relative
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(content)
    if not existing:
        codex_dir.mkdir(parents=True,exist_ok=True)
        if config.exists() and config.read_text(encoding="utf-8")!=old:
            raise SystemExit('Config changed concurrently; skill installed, MCP config not changed. Retry.')
        with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=codex_dir,delete=False) as out:
            out.write(updated)
            temp=Path(out.name)
        temp.chmod(0o600)
        temp.replace(config)
    print('Personal skill installed; career_discovery stdio MCP registered. No credentials copied.')
