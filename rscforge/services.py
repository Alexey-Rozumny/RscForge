from __future__ import annotations

import logging
import re
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx

from . import repositories as repo
from .config import settings
from .htmlparse import looks_like_html, parse_html
from .parsers import ParseResult, parse_text

logger = logging.getLogger(__name__)

USER_AGENT = "RscForge/0.1 (self-hosted address-list generator)"

MAX_ZERUM_PAGES = 500

_ZERUM_TEMPLATE_RE = re.compile(r'pagtemplate="([^"]+)"')
_ZERUM_WP_RE = re.compile(r"var\s+wp\s*=\s*['\"]([^'\"]+)['\"]")
_ZERUM_AJAX_RE = re.compile(
    r"var\s+ajax_path\s*=\s*wp\s*\+\s*['\"]([^'\"]+)['\"]"
)


class SourceFetchError(RuntimeError):
    pass


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


async def _read_url(url: str) -> tuple[str, str | None]:
    async with httpx.AsyncClient(
        timeout=settings.fetch_timeout,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type")
            chunks: list[bytes] = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > settings.max_fetch_bytes:
                    raise SourceFetchError(
                        f"Источник больше лимита {settings.max_fetch_bytes} байт"
                    )
                chunks.append(chunk)
    return _decode(b"".join(chunks)), content_type


def _zerum_endpoint(url: str, html: str) -> tuple[str, str] | None:
    """Detect Zerum CMS paginated lists and return (ajax_url, template)."""
    template = _ZERUM_TEMPLATE_RE.search(html)
    wp = _ZERUM_WP_RE.search(html)
    ajax = _ZERUM_AJAX_RE.search(html)
    if not (template and wp and ajax):
        return None

    ajax_url = urljoin(url, wp.group(1) + ajax.group(1))
    if urlsplit(ajax_url).netloc != urlsplit(url).netloc:
        return None
    return ajax_url, template.group(1)


async def _read_zerum(url: str, html: str) -> str | None:
    endpoint = _zerum_endpoint(url, html)
    if endpoint is None:
        return None
    ajax_url, template = endpoint

    async with httpx.AsyncClient(
        timeout=settings.fetch_timeout,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        response = await client.post(
            ajax_url,
            data={"type_zp": "pagtemplate_count", "pagtemplate": template},
        )
        response.raise_for_status()
        try:
            pages = int(response.json().get("data"))
        except (ValueError, TypeError, AttributeError):
            return None
        if pages < 1 or pages > MAX_ZERUM_PAGES:
            return None

        fragments: list[str] = []
        size = 0
        for page in range(1, pages + 1):
            response = await client.post(
                ajax_url,
                data={
                    "type_zp": "pagtemplate_create",
                    "pagtemplate": template,
                    "pageNum": page,
                    "formdata": "",
                    "search": "",
                    "sort": "",
                },
            )
            response.raise_for_status()
            try:
                fragment = response.json().get("data")
            except ValueError:
                return None
            if not isinstance(fragment, str):
                return None
            size += len(fragment.encode("utf-8"))
            if size > settings.max_fetch_bytes:
                raise SourceFetchError(
                    f"Источник больше лимита {settings.max_fetch_bytes} байт"
                )
            fragments.append(fragment)

    logger.info(
        "Zerum-источник %s: загружено %s страниц через %s",
        url,
        pages,
        ajax_url,
    )
    return "\n".join(fragments)


async def _parse_url(url: str) -> ParseResult:
    text, content_type = await _read_url(url)
    if not looks_like_html(text, content_type):
        return parse_text(text)

    expanded = await _read_zerum(url, text)
    if expanded is not None:
        return parse_html(expanded, url)
    if _zerum_endpoint(url, text) is not None:
        raise SourceFetchError("Не удалось загрузить постраничный список Zerum")
    return parse_html(text, url)


def _read_file(path: str) -> str:
    file_path = Path(path)
    if not file_path.is_file():
        raise SourceFetchError(f"Файл не найден: {path}")
    if file_path.stat().st_size > settings.max_fetch_bytes:
        raise SourceFetchError(
            f"Файл больше лимита {settings.max_fetch_bytes} байт"
        )
    return _decode(file_path.read_bytes())


async def refresh_source(source_id: int) -> dict:
    source = repo.get_source(source_id)
    if source is None:
        raise SourceFetchError("Источник не найден")

    try:
        if source["kind"] == "url":
            result = await _parse_url(source["url"])
        else:
            text = _read_file(source["stored_path"])
            result = parse_html(text) if looks_like_html(text) else parse_text(text)

        repo.replace_source_entries(source_id, result.entries)
        status = (
            f"ok: {len(result.entries)} записей, "
            f"пропущено {len(result.skipped)}"
        )
        repo.record_fetch(source_id, status=status, error=None)
    except Exception as exc:
        logger.warning("Не удалось обновить источник %s: %s", source_id, exc)
        repo.record_fetch(source_id, status=None, error=str(exc)[:500])
        raise

    updated = repo.get_source(source_id)
    assert updated is not None
    return updated


async def refresh_all() -> list[dict]:
    results: list[dict] = []
    for source in repo.list_sources():
        if not source["enabled"]:
            continue
        try:
            await refresh_source(source["id"])
            results.append({"id": source["id"], "name": source["name"], "ok": True})
        except Exception as exc:
            results.append(
                {
                    "id": source["id"],
                    "name": source["name"],
                    "ok": False,
                    "error": str(exc),
                }
            )
    return results
