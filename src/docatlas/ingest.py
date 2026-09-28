"""Bounded extraction with provenance. No crawling, executable markup or OCR."""

import hashlib
import io
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

from pypdf import PdfReader

SUPPORTED = {".md", ".markdown", ".txt", ".html", ".htm", ".pdf"}
MAX_CHARACTERS = 2_000_000
MAX_CHUNKS = 4000


@dataclass
class Chunk:
    id: str
    text: str
    section: str
    page: int | None
    ordinal: int


class VisibleHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.hidden += 1
        if tag in {"p", "div", "br", "li", "h1", "h2", "h3", "pre"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def extract(filename: str, content: bytes) -> list[tuple[int | None, str]]:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED:
        raise ValueError("Supported files: Markdown, TXT, HTML and text-based PDF.")
    if suffix == ".pdf":
        try:
            reader = PdfReader(io.BytesIO(content))
            if reader.is_encrypted or len(reader.pages) > 300:
                raise ValueError("PDF must be unencrypted and no more than 300 pages.")
            pages = []
            total = 0
            for i, page in enumerate(reader.pages):
                value = page.extract_text() or ""
                total += len(value)
                if total > MAX_CHARACTERS:
                    raise ValueError("Extracted text is too large.")
                pages.append((i + 1, value))
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("Unable to extract this PDF.") from exc
    else:
        try:
            value = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("Text files must use UTF-8 encoding.") from exc
        if suffix in {".html", ".htm"}:
            parser = VisibleHTML()
            parser.feed(value)
            value = "".join(parser.parts)
        pages = [(None, value)]
    if sum(len(text) for _, text in pages) > MAX_CHARACTERS:
        raise ValueError("Extracted text is too large.")
    if not any(text.strip() for _, text in pages):
        raise ValueError("No extractable text. Scanned PDFs require OCR before upload.")
    return pages


def chunk_document(document_id: str, pages, size: int = 1200, overlap: int = 180):
    if size < 100 or not 0 <= overlap < size:
        raise ValueError("Invalid chunk size or overlap.")
    chunks = []
    for page, value in pages:
        value = value.replace("\x00", "").replace("\r\n", "\n")
        sections = re.split(r"(?m)(?=^#{1,6} )", value)
        for section_text in sections:
            section_text = section_text.strip()
            if not section_text:
                continue
            heading = re.match(r"^#{1,6}\s+(.+)", section_text)
            section = heading.group(1)[:200] if heading else "Document"
            start = 0
            while start < len(section_text):
                end = min(start + size, len(section_text))
                if end < len(section_text):
                    boundary = section_text.rfind("\n", start + size // 2, end)
                    if boundary != -1:
                        end = boundary
                text = section_text[start:end].strip()
                if text:
                    ordinal = len(chunks)
                    key = f"{document_id}:{page}:{ordinal}:{text}"
                    chunks.append(Chunk(hashlib.sha256(key.encode()).hexdigest()[:24], text, section, page, ordinal))
                if len(chunks) > MAX_CHUNKS:
                    raise ValueError("Document produces too many chunks.")
                if end == len(section_text):
                    break
                start = end - overlap
    return chunks
