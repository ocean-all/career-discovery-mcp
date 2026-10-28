from __future__ import annotations

import re
from pathlib import PurePosixPath
from urllib.parse import urlsplit
from .core import Job, clean, digest, now, parse_deadline
from .extract import extract_document, html_page
from .http import FetchError

ATTACHMENT = re.compile(r"\.(pdf|hwpx?|png|jpe?g|webp|tiff?)(?:$|[?#])", re.I)
# Platforms require a separately negotiated API; they cannot be opted into this generic scraper.
BLOCKED = {"saramin.co.kr", "jobkorea.co.kr", "catch.co.kr", "jasoseol.com", "naver.com"}


def validate_sources(config):
    for host, rule in config.get("hosts", {}).items():
        if any(host == b or host.endswith("." + b) for b in BLOCKED):
            raise ValueError("Generic fetching of job platforms/Naver is disabled; use permitted APIs/manual discovery")
        if rule.get("allow_fetch") and not rule.get("permission_reference"):
            raise ValueError("Every enabled host needs a permission_reference")


def jobposting(structured):
    if isinstance(structured, list):
        for item in structured:
            found = jobposting(item)
            if found:
                return found
    elif isinstance(structured, dict):
        typ = structured.get("@type", [])
        if typ == "JobPosting" or isinstance(typ, list) and "JobPosting" in typ:
            return structured
        return jobposting(structured.get("@graph", []))
    return None


class Careers:
    def __init__(self, http, config):
        validate_sources(config)
        self.http, self.config = http, config

    def fetch(self, url):
        body, headers = self.http.get(url, policy=self.config["hosts"])
        ctype = headers.get("Content-Type", "")
        suffix = PurePosixPath(urlsplit(url).path).suffix
        if ATTACHMENT.search(url) or ctype.startswith("image/") or "application/pdf" in ctype:
            return extract_document(body, suffix, ctype)
        charset = headers.get_content_charset() if hasattr(headers, "get_content_charset") else None
        return html_page(body, url, charset or "utf-8")

    def collect(self, on_error):
        seen = set()
        queue = list(self.config.get("pages", []))
        for page in queue:
            url = page["url"]
            if url in seen:
                continue
            seen.add(url)
            try:
                extracted = self.fetch(url)
                if page.get("kind") == "index":
                    pattern = page.get("link_pattern")
                    if not pattern:
                        raise FetchError("index requires a link_pattern")
                    links = [(u,t) for u,t in extracted.links if re.search(pattern,u)]
                    if len(links) > 30:
                        on_error("careers index truncated to 30 matching links")
                    for u,title in links[:30]:
                        queue.append({**page, "url":u, "title":title, "kind":"posting"})
                    continue
                yield self.posting(page, extracted)
            except (FetchError, ValueError, KeyError) as exc:
                # Exceptions from HTTP contain no secrets. Don't log arbitrary remote content.
                on_error(f"careers {urlsplit(url).hostname}: {type(exc).__name__}: {exc}")

    def posting(self, page, extracted):
        url = page["url"]
        attachments = []
        warnings = list(extracted.warnings)
        text = extracted.text
        links = [(u,t) for u,t in extracted.links if ATTACHMENT.search(u)]
        links += [(u,"image") for u in extracted.images if ATTACHMENT.search(u)]
        for u, _ in list(dict.fromkeys(links))[:8]:
            try:
                doc = self.fetch(u)
                text += "\n" + doc.text
                attachments.append({"url": u, "method": doc.method, "warnings": doc.warnings, "text_hash": digest(clean(doc.text))})
                warnings.extend(doc.warnings)
            except FetchError:
                attachments.append({"url": u, "method":"unread", "warnings":["permission/robots/network denied; manual review"]})
                warnings.append("attachment not read")
        jd = jobposting(extracted.structured) or {}
        if jd.get("description"):
            text += "\n" + clean(jd["description"])
        # A known host alone isn't proof of the posting's identity or applicability.
        terms = page.get("expected_terms", [])
        identity = bool(terms) and all(t.casefold() in clean(text).casefold() for t in terms)
        has_content = len(clean(text)) >= 60
        status = "original_identity_matched" if identity and has_content and not warnings else "original_needs_review"
        confidence = .85 if status == "original_identity_matched" else .45 if has_content else .1
        deadline = page.get("deadline")
        if not deadline and jd.get("validThrough"):
            # Structured dates can include timezone or a date only. Interpret date-only as KST end of day.
            value = jd["validThrough"]
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                deadline = value + "T23:59:59+09:00"
            elif re.search(r"(?:Z|[+-]\d\d:\d\d)$", value):
                deadline = value.replace("Z", "+00:00")
        if not deadline:
            deadline = parse_deadline(clean(text))
        return Job(source="company", source_id=digest(url), url=url,
                   title=page.get("title") or clean(jd.get("title")) or clean(extracted.title) or "제목 미확인",
                   company=page.get("company") or clean(jd.get("hiringOrganization", {})),
                   text=text, deadline=deadline, verification=status, confidence=confidence,
                   evidence=[{"url":url, "kind":"employer_original", "retrieved_at":now().isoformat(),
                              "expected_terms_matched":identity, "warnings":warnings,
                              "discovered_via":page.get("discovered_via", "configured") }],
                   attachments=attachments)
