from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from .parsers import ParseResult, parse_text, parse_value

SKIP_TAGS = {"script", "style", "noscript", "template", "head", "svg"}

ASSET_SUFFIXES = {
    "css",
    "js",
    "mjs",
    "map",
    "html",
    "htm",
    "php",
    "xml",
    "json",
    "txt",
    "pdf",
    "zip",
    "gz",
    "tar",
    "png",
    "jpg",
    "jpeg",
    "gif",
    "svg",
    "ico",
    "webp",
    "woff",
    "woff2",
    "ttf",
    "otf",
    "eot",
}


class _Extractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.chunks: list[str] = []
        self.links: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in SKIP_TAGS:
            self._skip_depth += 1
            return
        for name, value in attrs:
            if name in {"href", "src"} and value:
                self.links.append(value)

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag not in SKIP_TAGS:
            self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth and data.strip():
            self.chunks.append(data)


def looks_like_html(text: str, content_type: str | None = None) -> bool:
    if content_type and "html" in content_type.lower():
        return True
    head = text.lstrip()[:1024].lower()
    return (
        head.startswith("<!doctype html")
        or "<html" in head
        or "<body" in head
        or "<head" in head
    )


def _external_host(link: str, base_url: str | None) -> str | None:
    if link.startswith(("#", "data:", "javascript:", "mailto:", "tel:")):
        return None
    absolute = urljoin(base_url or "", link)
    parts = urlsplit(absolute)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return None
    if base_url:
        base_host = urlsplit(base_url).hostname
        if base_host and parts.hostname.lower() == base_host.lower():
            return None
    return parts.hostname


def parse_html(html: str, base_url: str | None = None) -> ParseResult:
    """Extract domains/IPs from visible page text and external links."""
    extractor = _Extractor()
    extractor.feed(html)
    extractor.close()

    result = parse_text("\n".join(extractor.chunks))
    result.entries = [
        entry
        for entry in result.entries
        if not (
            entry.kind == "domain"
            and entry.normalized.rsplit(".", 1)[-1] in ASSET_SUFFIXES
        )
    ]

    seen = {entry.normalized for entry in result.entries}
    for link in extractor.links:
        host = _external_host(link, base_url)
        if not host:
            continue
        parsed = parse_value(host)
        if parsed is None or parsed.normalized in seen:
            continue
        seen.add(parsed.normalized)
        result.entries.append(parsed)

    return result
