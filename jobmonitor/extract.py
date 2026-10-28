"""Local document extraction. No document content is sent to an AI service."""
from __future__ import annotations

import io
import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin
from xml.etree import ElementTree


@dataclass
class Extraction:
    text: str = ""
    method: str = ""
    warnings: list = field(default_factory=list)
    links: list = field(default_factory=list)
    images: list = field(default_factory=list)
    title: str = ""
    structured: list = field(default_factory=list)


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.links, self.images, self.structured = [], [], [], []
        self.skip = 0
        self.title_parts = []
        self.in_title = False
        self.json_script = False
        self.script = []
        self.anchor = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"script", "style", "nav", "header", "footer", "noscript"}:
            self.skip += 1
        if tag == "script" and attrs.get("type") == "application/ld+json":
            self.json_script = True
            self.script = []
        if tag == "title":
            self.in_title = True
        if tag == "a" and attrs.get("href"):
            self.anchor = [attrs["href"], []]
        if tag == "img":
            src = attrs.get("src") or attrs.get("data-src")
            if src:
                self.images.append(src)

    def handle_endtag(self, tag):
        if tag == "script" and self.json_script:
            try:
                self.structured.append(json.loads("".join(self.script)))
            except ValueError:
                pass
            self.json_script = False
        if tag in {"script", "style", "nav", "header", "footer", "noscript"}:
            self.skip = max(0, self.skip - 1)
        if tag == "title":
            self.in_title = False
        if tag == "a" and self.anchor:
            self.links.append((self.anchor[0], " ".join(self.anchor[1])))
            self.anchor = None

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data)
        if self.json_script:
            self.script.append(data)
        if not self.skip:
            self.parts.append(data)
        if self.anchor:
            self.anchor[1].append(data)


def html_page(body, base, charset="utf-8"):
    parser = Page()
    parser.feed(body.decode(charset, "replace"))
    return Extraction(text=" ".join(parser.parts), method="html",
                      links=[(urljoin(base,u), t) for u,t in parser.links],
                      images=[urljoin(base,u) for u in parser.images],
                      title=" ".join(parser.title_parts), structured=parser.structured)


def run_tool(args, timeout=90):
    try:
        p = subprocess.run(args, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return "", "converter unavailable/timeout"
    if p.returncode:
        return "", "converter failed (details omitted)"
    return p.stdout.decode("utf-8", "replace"), ""


def ocr_image(path):
    if not shutil.which("tesseract"):
        return "", "tesseract missing; install Korean and English language data"
    return run_tool(["tesseract", str(path), "stdout", "-l", "kor+eng"], 90)


def extract_document(body, suffix, content_type=""):
    suffix = suffix.lower()
    if body.startswith(b"%PDF") or suffix == ".pdf" or "application/pdf" in content_type:
        return extract_pdf(body)
    if suffix == ".hwpx":
        try:
            with zipfile.ZipFile(io.BytesIO(body)) as archive:
                names = sorted(n for n in archive.namelist() if re.fullmatch(r"Contents/section\d+\.xml", n))
                if sum(i.file_size for i in archive.infolist()) > 30 * 1024 * 1024:
                    return Extraction(method="hwpx", warnings=["HWPX uncompressed size limit exceeded"])
                parts = []
                for name in names[:40]:
                    root = ElementTree.fromstring(archive.read(name))
                    parts.extend(e.text for e in root.iter() if e.tag.rsplit("}",1)[-1] == "t" and e.text)
                return Extraction(" ".join(parts), "hwpx", ["tables/layout require manual review"])
        except (zipfile.BadZipFile, ElementTree.ParseError):
            return Extraction(method="hwpx", warnings=["invalid HWPX"])
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / ("input" + suffix)
        path.write_bytes(body)
        if suffix == ".hwp":
            if shutil.which("hwp5txt"):
                text, warning = run_tool(["hwp5txt", str(path)])
                return Extraction(text, "hwp5txt", [warning] if warning else ["HWP conversion requires manual review"])
            return Extraction(method="hwp", warnings=["optional hwp5txt missing; export to PDF/HWPX manually"])
        if suffix in {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"} or content_type.startswith("image/"):
            text, warning = ocr_image(path)
            return Extraction(text, "ocr", [warning] if warning else ["OCR output: manually verify dates and requirements"])
    return Extraction(method="unsupported", warnings=["unsupported attachment type"])


def extract_pdf(body):
    warnings, parts = [], []
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "input.pdf"
        path.write_bytes(body)
        # Per-page fallback handles mixed scanned/text PDFs.
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(body))
            if len(reader.pages) > 30:
                warnings.append("PDF truncated to first 30 pages")
            pages = [(i + 1, p.extract_text() or "") for i,p in enumerate(reader.pages[:30])]
        except ImportError:
            if shutil.which("pdftotext"):
                text, warning = run_tool(["pdftotext", "-f", "1", "-l", "30", str(path), "-"])
                pages = list(enumerate(text.split("\f"), 1))
                if pages and not pages[-1][1].strip():
                    pages.pop()
                if warning:
                    warnings.append(warning)
            else:
                return Extraction(method="pdf", warnings=["pypdf or Poppler required"])
        except Exception:
            return Extraction(method="pdf", warnings=["PDF parsing failed/encrypted; manual review required"])
        for page, text in pages:
            if len(text.strip()) < 30:
                if shutil.which("pdftoppm") and shutil.which("tesseract"):
                    prefix = str(Path(tmp) / f"page-{page}")
                    _, warning = run_tool(["pdftoppm", "-f", str(page), "-l", str(page), "-scale-to", "2500", "-singlefile", "-png", str(path), prefix])
                    scanned, ocr_warning = ocr_image(Path(prefix + ".png")) if not warning else ("", warning)
                    text = scanned or text
                    warnings.extend([f"page {page}: {ocr_warning}" if ocr_warning else f"page {page}: OCR, manual review"])
                else:
                    warnings.append(f"page {page}: scanned/empty; Poppler + tesseract kor+eng required")
            parts.append(f"[page {page}] {text}")
    return Extraction("\n".join(parts), "pdf", warnings)
