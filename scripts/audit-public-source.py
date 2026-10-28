"""Scan tracked source or one reachable Git history. Never print matched secret values."""
import argparse
import json
import re
import subprocess
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument('--ref',help='Scan all blobs reachable from this ref; otherwise scan tracked working files')
parser.add_argument('--deny-values-file',type=Path,help='Private dotenv file; values are only compared locally')
parser.add_argument('--deny-pattern',action='append',default=[])
args=parser.parse_args()
secrets=[]
if args.deny_values_file:
    for line in args.deny_values_file.read_text(encoding="utf-8").splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key,value=line.split('=',1)
            value=value.strip().strip('\"\'')
            if value and any(t in key.upper() for t in ['SECRET','KEY','CLIENT_ID']):
                secrets.append(value.encode())
patterns=[re.compile(p,re.I) for p in args.deny_pattern]
objects=[]
if args.ref:
    lines=subprocess.check_output(['git','rev-list','--objects',args.ref]).decode().splitlines()
    for line in lines:
        oid,*name=line.split(' ',1)
        kind=subprocess.check_output(['git','cat-file','-t',oid]).strip()
        if kind==b'blob':
            objects.append((name[0] if name else oid,subprocess.check_output(['git','cat-file','blob',oid])))
else:
    for name in subprocess.check_output(['git','ls-files','-z']).decode().split('\0'):
        if name and Path(name).is_file(): objects.append((name,Path(name).read_bytes()))
issues=[]
for name,body in objects:
    if any(value in body for value in secrets):
        issues.append({'path':name,'kind':'private_credential_value'})
    text=body.decode('utf-8','replace')
    if any(pattern.search(text) or pattern.search(name) for pattern in patterns):
        issues.append({'path':name,'kind':'denied_identity_or_background_pattern'})
    if name.split('/')[-1] in {'.env','profile.json','local-installation.json'} or name.endswith(('.sqlite','.sqlite-wal')):
        issues.append({'path':name,'kind':'private_runtime_file'})
print(json.dumps({'scope':args.ref or 'tracked_working_files','objects_scanned':len(objects),'issues':issues,'passed':not issues},ensure_ascii=False))
raise SystemExit(bool(issues))
