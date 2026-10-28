"""Keyless public discovery links; never impersonates an authenticated API collector."""
from urllib.parse import urlencode
from .google_discovery import search_links


def search_links_for_queries(queries, days=30):
    links=[]
    for query in list(dict.fromkeys(queries))[:24]:
        if not isinstance(query,str) or not query.strip() or len(query)>180:
            raise ValueError("Search queries must be nonempty text up to 180 characters")
        links.append({"query":query,"saramin_url":"https://www.saramin.co.kr/zf_user/search?"+urlencode({"searchword":query}),
                      "google_url":search_links('site:saramin.co.kr '+query,days)['links'][0]['url']})
    return {"mode":"public_search_links","api_key_required":False,"automatically_collected":False,
            "days":days,"links":links,
            "warning":"Open these public searches and verify original postings. Google dates are page dates; no API data or job details were fetched. Official API collection remains optional and requires a user-owned key."}
