from __future__ import annotations

import os
from datetime import datetime
from .core import Job, KST, clean, now
from .http import FetchError


def saramin_job(raw):
    p = raw.get("position", {})
    exp = p.get("experience-level", {})
    company = raw.get("company", {}).get("detail", raw.get("company", {}))
    close = raw.get("close-type", {})
    code = close.get("code") if isinstance(close, dict) else close
    deadline = None
    if str(code) == "1" and str(raw.get("expiration-timestamp", "")).isdigit():
        deadline = datetime.fromtimestamp(int(raw["expiration-timestamp"]), KST).isoformat()
    if not raw.get("id") or not raw.get("url") or not p.get("title"):
        raise FetchError("Saramin job missing id/url/title")
    return Job(
        source="saramin", source_id=str(raw["id"]), url=raw["url"],
        title=clean(p["title"]), company=clean(company),
        text=" ".join(clean(v) for v in [p.get("industry"), p.get("job-code"), exp, p.get("required-education-level"), raw.get("keyword")]),
        location=clean(p.get("location")), deadline=deadline,
        active="open" if str(raw.get("active")) == "1" else "closed" if str(raw.get("active")) == "0" else "unknown",
        verification="official_api_metadata", confidence=.75,
        evidence=[{"url": raw["url"], "kind": "saramin_official_api", "retrieved_at": now().isoformat(), "scope": "metadata only; detailed JD not verified"}],
        experience_code=str(exp.get("code")) if isinstance(exp, dict) else None,
    )


class Saramin:
    def __init__(self, http, config):
        self.http, self.config = http, config

    def collect(self):
        key = os.getenv("SARAMIN_ACCESS_KEY")
        if not key:
            return  # keyless mode is public discovery, never unauthorized API access
        cfg = self.config
        if not cfg.get("queries"):
            raise FetchError("No search scope: discuss interests and save a confirmed profile first")
        for query in cfg["queries"]:
            previous = None
            for page in range(cfg.get("pages_per_query", 2)):
                result = self.http.json("https://oapi.saramin.co.kr/job-search",
                    {"access-key": key, "keywords": query, "start": page, "count": 110, "sort": "ud"},
                    headers={"Accept": "application/json"}, reserve=("saramin", min(500, cfg.get("daily_budget", 100))))
                if "jobs" not in result:
                    raise FetchError(f"Saramin API error code {result.get('code', 'unknown')}; check credentials/quota")
                jobs = result["jobs"].get("job", [])
                if isinstance(jobs, dict):
                    jobs = [jobs]
                ids = tuple(str(j.get("id")) for j in jobs)
                if ids and ids == previous:
                    raise FetchError("Saramin repeated page; results truncated")
                previous = ids
                for raw in jobs:
                    yield saramin_job(raw)
                if len(jobs) < 110 or (page + 1) * 110 >= int(result["jobs"].get("total", 0)):
                    break


class Naver:
    """Transient search display only. Never sends results into Store or scoring."""
    def __init__(self, http):
        self.http = http

    def search(self, query, start=1, display=10):
        cid, secret = os.getenv("NAVER_CLIENT_ID"), os.getenv("NAVER_CLIENT_SECRET")
        if not cid or not secret:
            raise FetchError("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET missing")
        if not 1 <= start <= 1000 or not 1 <= display <= 100:
            raise ValueError("Invalid Naver pagination")
        mode = os.getenv("NAVER_MODE", "hub")
        if mode == "hub":
            url = "https://naverapihub.apigw.ntruss.com/search/v1/blog"
            headers = {"X-NCP-APIGW-API-KEY-ID": cid, "X-NCP-APIGW-API-KEY": secret}
        elif mode == "legacy":
            url = "https://openapi.naver.com/v1/search/blog.json"
            headers = {"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": secret}
        else:
            raise ValueError("NAVER_MODE must be hub or legacy")
        value = self.http.json(url, {"query": query, "start": start, "display": display, "sort": "date"},
                               headers=headers, reserve=("naver", 100))
        if "items" not in value:
            raise FetchError("Naver error response; inspect application access in console")
        return value
