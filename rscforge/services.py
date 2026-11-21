from __future__ import annotations

import logging
from pathlib import Path

import httpx

from . import repositories as repo
from .config import settings
from .parsers import parse_text

logger = logging.getLogger(__name__)

USER_AGENT = "RscForge/0.1 (self-hosted address-list generator)"


class SourceFetchError(RuntimeError):
    pass


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


async def _read_url(url: str) -> str:
    async with httpx.AsyncClient(
        timeout=settings.fetch_timeout,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            chunks: list[bytes] = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > settings.max_fetch_bytes:
                    raise SourceFetchError(
                        f"Источник больше лимита {settings.max_fetch_bytes} байт"
                    )
                chunks.append(chunk)
    return _decode(b"".join(chunks))


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
            text = await _read_url(source["url"])
        else:
            text = _read_file(source["stored_path"])

        result = parse_text(text)
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
