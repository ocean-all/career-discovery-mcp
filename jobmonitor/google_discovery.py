"""Generate date-bounded Google search links, without scraping search results."""
from datetime import timedelta
from urllib.parse import urlencode
from .core import now

SITES = ["saramin.co.kr", "jobkorea.co.kr", "catch.co.kr", "jasoseol.com"]


def search_links(query="", days=30, at=None):
    if not query.strip() or not 1 <= days <= 365 or len(query) > 200:
        raise ValueError("query is required (up to 200 characters); days must be 1–365")
    at = at or now()
    start = (at.date() - timedelta(days=days)).isoformat()
    end = (at.date() + timedelta(days=1)).isoformat()
    queries = [query.strip()]
    links = []
    for text in queries:
        full = f"{text} after:{start} before:{end}"
        links.append({"query": full, "url": "https://www.google.com/search?" + urlencode({"q": full,"hl":"ko"})})
    return {"provider":"google", "mode":"search_links_only", "days":days,
            "after":start,"before":end,"links":links,
            "warning":"Date filters concern Google's page dates, not recruitment deadlines. Verify the filter and original posting; older open jobs may be missed."}
