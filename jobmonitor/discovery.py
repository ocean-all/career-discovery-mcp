"""Loopback-only transient Naver search viewer. No search results are persisted."""
import html
import secrets
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit


def safe_link(value):
    p = urlsplit(value)
    return value if p.scheme in {"http", "https"} and p.hostname and not p.username else "#"


def formatted(value):
    # Only the API's <b> emphasis is rendered; all other markup is inert.
    return html.escape(str(value)).replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>")


def render_results(result):
    parts = ['<section><h2>네이버 검색결과</h2><p><a href="https://www.naver.com/">NAVER</a> · API 제공 순서 · 가공·재정렬·저장 없음</p><ol>']
    for item in result["items"]:
        href = html.escape(safe_link(item.get("link", "")), quote=True)
        blog = html.escape(safe_link(item.get("bloggerlink", "")), quote=True)
        parts.append(f'<li><a rel="noreferrer" target="_blank" href="{href}">{formatted(item.get("title", ""))}</a><p>{formatted(item.get("description", ""))}</p><p><a href="{blog}">{html.escape(item.get("bloggername", ""))}</a> · {html.escape(item.get("postdate", ""))}</p></li>')
    return "".join(parts) + "</ol></section>"


def serve(naver, port=8765):
    token = secrets.token_urlsafe(32)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def page(self, content, status=200):
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Content-Security-Policy", "default-src 'none'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(content.encode())

        def valid_host(self):
            return self.headers.get("Host") == f"127.0.0.1:{port}"

        def shell(self, content=""):
            return f'''<!doctype html><html lang="ko"><meta charset="utf-8"><title>채용 발견 검색</title>
            <h1>채용 발견 검색</h1><p>검색 결과는 이 화면에서만 확인합니다. 회사 원문을 직접 확인한 후 sources.json에 독립적으로 등록하세요.</p>
            <form method="post" action="/"><input type="hidden" name="token" value="{token}"><label>검색어 <input name="q" required maxlength="200" value="물류 학력무관 신입 채용"></label><button>검색</button></form>
            {content}</html>'''

        def do_GET(self):
            if not self.valid_host() or self.path != "/":
                self.page("Invalid request", 400)
                return
            self.page(self.shell())

        def do_POST(self):
            if not self.valid_host() or self.path != "/":
                self.page("Invalid request", 400)
                return
            origin = self.headers.get("Origin")
            if origin and origin != f"http://127.0.0.1:{port}":
                self.page("Invalid origin", 403)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > 4096:
                    raise ValueError()
                form = parse_qs(self.rfile.read(length).decode())
                if not secrets.compare_digest(form.get("token", [""])[0], token):
                    self.page("Invalid token", 403)
                    return
                query = form.get("q", [""])[0].strip()
                if not query or len(query) > 200:
                    raise ValueError()
                result = naver.search(query)
                self.page(self.shell(render_results(result)))
            except Exception:
                self.page(self.shell("<p>검색 실패: 키·앱 권한·할당량·네트워크를 확인하세요.</p>"), 502)
    print(f"네이버 검색 화면: http://127.0.0.1:{port}/ (종료: Ctrl+C)")
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
