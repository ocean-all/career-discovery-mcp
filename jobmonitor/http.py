"""Bounded HTTPS, no ambient proxy/cookies, explicit redirects and retry budgets."""
from __future__ import annotations

import ipaddress
import json
import os
import socket
import ssl
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.robotparser import RobotFileParser


class FetchError(RuntimeError):
    pass


def public_https(url):
    p = urlsplit(url)
    if p.scheme != "https" or not p.hostname or p.username or p.password or p.port not in (None, 443):
        raise FetchError("Only public HTTPS URLs on port 443 are accepted")
    try:
        addresses = socket.getaddrinfo(p.hostname, 443, type=socket.SOCK_STREAM)
    except OSError:
        raise FetchError("DNS lookup failed") from None
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise FetchError("Private/local network targets are blocked")
    return p.hostname.lower()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HTTP:
    def __init__(self, store=None, user_agent=None, sleep=time.sleep):
        self.store = store
        self.ua = user_agent or os.getenv("JOBMONITOR_USER_AGENT", "RetailJobMonitor/0.1")
        try:
            import certifi
            context = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            context = ssl.create_default_context()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
            urllib.request.HTTPSHandler(context=context), NoRedirect())
        self.sleep = sleep
        self.last = {}
        self.robots = {}

    def get(self, url, *, headers=None, reserve=None, policy=None, robots=True, redirects=0):
        host = public_https(url)
        if policy is not None:
            rule = policy.get(host)
            if not rule or not rule.get("permission_reference") or not rule.get("allow_fetch"):
                raise FetchError("Host lacks documented permission in sources.json")
            if robots:
                self.check_robots(url, policy)
        wait = max(0, self.last.get(host, 0) + 1.1 - time.monotonic())
        if wait:
            self.sleep(wait)
        for attempt in range(3):
            if reserve:
                if self.store is None:
                    raise FetchError("Persistent quota store required")
                self.store.reserve(*reserve)
            req = urllib.request.Request(url, headers={"User-Agent": self.ua, **(headers or {})})
            try:
                self.last[host] = time.monotonic()
                with self.opener.open(req, timeout=25) as response:
                    result = bytearray()
                    while chunk := response.read(65536):
                        result.extend(chunk)
                        if len(result) > 15 * 1024 * 1024:
                            raise FetchError("Response exceeds 15 MiB")
                    return bytes(result), response.headers
            except urllib.error.HTTPError as exc:
                if exc.code in (301, 302, 303, 307, 308):
                    target = urljoin(url, exc.headers.get("Location", ""))
                    exc.close()
                    if reserve or redirects >= 3 or policy is None:
                        raise FetchError("Redirect blocked (API credentials are never forwarded)") from None
                    return self.get(target, policy=policy, redirects=redirects + 1)
                if exc.code in (429, 500, 502, 503, 504) and attempt < 2:
                    delay = exc.headers.get("Retry-After", "")
                    if delay.isdigit() and int(delay) > 30:
                        exc.close()
                        raise FetchError("Provider requested longer backoff; retry on next run") from None
                    exc.close()
                    self.sleep(max(2 ** attempt, int(delay) if delay.isdigit() else 0))
                    continue
                status = exc.code
                exc.close()
                raise FetchError(f"HTTP {status}; no response URL or credential logged") from None
            except (urllib.error.URLError, TimeoutError, OSError):
                if attempt == 2:
                    raise FetchError("Network/timeout failure; details redacted") from None
                self.sleep(2 ** attempt)
        raise FetchError("Retry exhausted")

    def check_robots(self, url, policy):
        p = urlsplit(url)
        origin = f"https://{p.netloc}"
        if origin not in self.robots:
            try:
                body, _ = self.get(origin + "/robots.txt", policy=policy, robots=False)
            except FetchError as exc:
                if str(exc).startswith("HTTP 404"):
                    body = b"User-agent: *\nAllow: /\n"
                else:
                    raise FetchError("robots.txt unavailable; fetch deferred") from None
            parser = RobotFileParser()
            parser.parse(body.decode("utf-8", "replace").splitlines())
            self.robots[origin] = parser
        parser = self.robots[origin]
        if not parser.can_fetch(self.ua, url):
            raise FetchError("robots.txt disallows this URL")
        delay = parser.crawl_delay(self.ua) or parser.crawl_delay("*") or 0
        if delay > 30:
            raise FetchError("robots crawl delay exceeds supported wait; manual review")
        wait = self.last.get(p.hostname, 0) + max(1.1, delay) - time.monotonic()
        if wait > 0:
            self.sleep(wait)

    def json(self, base, params, *, headers, reserve):
        body, _ = self.get(base + "?" + urlencode(params), headers=headers, reserve=reserve)
        try:
            value = json.loads(body)
        except (ValueError, UnicodeError):
            raise FetchError("API returned non-JSON data") from None
        if not isinstance(value, dict):
            raise FetchError("API JSON object expected")
        return value
