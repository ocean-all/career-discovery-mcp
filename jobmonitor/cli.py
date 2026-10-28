from __future__ import annotations

import argparse
from filelock import FileLock, Timeout
import json
import os
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

from .careers import Careers
from .core import Job, KST, Store, now
from .discovery import serve
from .extract import extract_document
from .http import HTTP, FetchError
from .providers import Naver, Saramin


def load_env(path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            if key.strip().replace("_", "").isalnum():
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as f:
        f.write(text)
        temp = Path(f.name)
    temp.replace(path)


def run(root, store, demo=False):
    started = now().isoformat()
    cur = store.db.execute("INSERT INTO runs(started,status,details) VALUES(?,?,?)", (started, "running", ""))
    run_id = cur.lastrowid
    store.db.commit()
    messages = []
    count = 0
    saramin_discovery = None
    company_pages_configured = False
    def failure(message):
        messages.append(message)
    http = HTTP(store)
    failed = False
    if demo:
        fixture = json.loads((root / "examples/demo-jobs.json").read_text(encoding="utf-8"))
        sources = [("demo", (Job(**j) for j in fixture))]
    else:
        try:
            cfg = json.loads((root / "config.json").read_text(encoding="utf-8"))
            from .profile import load, search_plan
            profile=load(root)
            plan=search_plan(profile)
            store.profile=profile  # neutral, user-configurable scoring; never assumes retail
            if plan['ready']:
                cfg['saramin']['queries']=plan['saramin_keywords']
            pages = json.loads((root / "sources.json").read_text(encoding="utf-8"))
            careers = Careers(http, pages)
            company_pages_configured = bool(pages.get("pages"))
            if not os.getenv("SARAMIN_ACCESS_KEY"):
                from .saramin_discovery import search_links_for_queries
                saramin_discovery = search_links_for_queries(cfg["saramin"].get("queries",[]), profile.get("days",30))
                atomic_write(root / "reports/saramin-discovery.json",json.dumps(saramin_discovery,ensure_ascii=False,indent=2))
                messages.append("Saramin: keyless public search links only; no API results collected. Open reports/saramin-discovery.json and verify originals.")
            sources = [("saramin", Saramin(http, cfg["saramin"]).collect()), ("careers", careers.collect(failure))]
            if not pages.get("pages"):
                messages.append("company pages: none configured (not searched)")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            failed = True
            sources = []
            failure(f"configuration: {type(exc).__name__}; check config.json and sources.json")
        messages.append("Naver: separate transient discovery viewer; JobKorea/Catch/Jasoseol: manual search only")
    for name, jobs in sources:
        try:
            for job in jobs:
                store.upsert(job)
                count += 1
        except (RuntimeError, ValueError, KeyError, TypeError) as exc:
            failed = True
            failure(f"{name}: {type(exc).__name__}: {exc}")
    # Careers can continue after individual errors; those still make this run partial.
    failed = failed or any(m.startswith("careers ") for m in messages)
    status = "demo" if demo else "partial" if failed else "discovery_only" if saramin_discovery is not None and not company_pages_configured else "ok"
    details = json.dumps({"observations":count, "messages":messages}, ensure_ascii=False)
    with store.db:
        store.db.execute("UPDATE runs SET finished=?,status=?,details=? WHERE id=?", (now().isoformat(), status, details, run_id))
    report = store.report()
    if saramin_discovery is not None:
        report += "\n## 사람인 공개 검색 — API 키 불필요\n\n자동 수집한 공고가 아닙니다. 링크에서 후보를 찾고 회사 원문을 확인하세요.\n\n"
        if not saramin_discovery['links']:
            report += "확정된 검색 범위가 없습니다. 먼저 관심 직무·산업을 정하거나 명시적 검색어를 입력하세요.\n"
        for i,link in enumerate(saramin_discovery['links'][:12],1):
            report += f"- 검색 {i}: [사람인 공개 검색]({link['saramin_url']}) · [최근 기간 Google 검색]({link['google_url']})\n"
        if len(saramin_discovery['links'])>12:
            report += "전체 링크는 reports/saramin-discovery.json에 있습니다.\n"

    if demo:
        report = "**DEMO: 아래 공고는 가상 테스트 자료입니다. 실제 채용정보가 아닙니다.**\n\n" + report
    out = root / ("reports/demo" if demo else "reports")
    atomic_write(out / f"{now():%Y-%m-%d}.md", report)
    atomic_write(out / "latest.md", report)
    print(f"{status}: {count} observations; report={out / 'latest.md'}")
    return 2 if failed else 0


def next_run(at):
    target = at.astimezone(KST).replace(hour=9, minute=0, second=0, microsecond=0)
    return target if at < target else target + timedelta(days=1)


def schedule(root, store):
    marker = root / "data/schedule-last-date"
    print("Local scheduler running: daily 09:00 Asia/Seoul. Keep this process and computer running.", flush=True)
    while True:
        at = now()
        today = at.date().isoformat()
        last = marker.read_text(encoding="utf-8").strip() if marker.exists() else ""
        if at.hour >= 9 and last != today:
            try:
                with FileLock(root / "data/monitor.lock", timeout=0):
                    run(root, store)
            except Exception as exc:
                # Keep service alive without printing remote body, URLs containing keys, or traceback.
                print(f"Scheduled run failed: {type(exc).__name__}; review configuration", flush=True)
            atomic_write(marker, today)
        remaining = (next_run(now()) - now()).total_seconds()
        time.sleep(max(1, min(60, remaining)))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Korean career monitor")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run")
    sub.add_parser("demo")
    sub.add_parser("report")
    sub.add_parser("schedule")
    discovery = sub.add_parser("discover")
    discovery.add_argument("--port", type=int, default=8765)
    extract = sub.add_parser("extract")
    extract.add_argument("path", type=Path)
    extract.add_argument("--output", type=Path, required=True)
    saramin_parser = sub.add_parser("saramin-links")
    saramin_parser.add_argument("--query", default="")
    saramin_parser.add_argument("--days",type=int,default=30)
    links_parser = sub.add_parser("search-links")
    links_parser.add_argument("--days", type=int, default=30)
    links_parser.add_argument("--query", default="")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    load_env(root / ".env")
    if args.command == "extract":
        if args.path.stat().st_size > 15 * 1024 * 1024:
            parser.error("Local document exceeds 15 MiB")
        result = extract_document(args.path.read_bytes(), args.path.suffix)
        atomic_write(args.output, json.dumps(result.__dict__, ensure_ascii=False, indent=2))
        print(f"Extracted using {result.method}; warnings={result.warnings}")
        return 0
    if args.command == "saramin-links":
        from .saramin_discovery import search_links_for_queries
        from .profile import load,search_plan
        p=load(root)
        plan=search_plan(p)
        queries=[args.query] if args.query.strip() else plan.get('saramin_keywords',[])
        print(json.dumps(search_links_for_queries(queries,args.days),ensure_ascii=False,indent=2))
        return 0
    if args.command == "search-links":
        from .google_discovery import search_links
        if args.query.strip():
            values=[search_links(args.query,args.days)]
        else:
            from .profile import load,search_plan
            plan=search_plan(load(root))
            if not plan['ready']:
                print(plan['message'])
                return 2
            values=[search_links(q,plan['days']) for q in plan['queries']]
        for value in values:
            for link in value["links"]:
                print(link["query"] + "\n" + link["url"])
        print(values[0]["warning"] if values else "No accepted search terms")
        return 0
    (root / "data").mkdir(exist_ok=True)
    db = root / ("data/demo.sqlite" if args.command == "demo" else "data/jobs.sqlite")
    store = Store(db)
    # Long-running viewer/scheduler must not block independent manual runs.
    lock = FileLock(root / "data/monitor.lock", timeout=0)
    try:
        if args.command in {"run", "demo"}:
            lock.acquire()
    except Timeout:
        store.close()
        print("Another monitor command is running. Retry after it finishes.")
        return 3
    try:
        if args.command in {"run", "demo"}:
            return run(root, store, demo=args.command == "demo")
        if args.command == "report":
            report = store.report()
            atomic_write(root / "reports/latest.md", report)
            print(root / "reports/latest.md")
        elif args.command == "discover":
            # Discovery uses its own DB for quota only, never for search content.
            serve(Naver(HTTP(store)), args.port)
        elif args.command == "schedule":
            schedule(root, store)
    finally:
        lock.release()
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
