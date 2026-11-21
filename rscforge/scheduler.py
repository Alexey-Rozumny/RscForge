from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from . import repositories as repo
from .services import refresh_source

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 60


def _is_due(source: dict) -> bool:
    last_fetched = source.get("last_fetched_at")
    if not last_fetched:
        return True
    try:
        last_dt = datetime.fromisoformat(last_fetched)
    except ValueError:
        return True
    if last_dt.tzinfo is None:
        last_dt = last_dt.replace(tzinfo=timezone.utc)
    interval = max(5, int(source.get("refresh_interval_minutes") or 60))
    return datetime.now(timezone.utc) >= last_dt + timedelta(minutes=interval)


async def scheduler_loop(stop_event: asyncio.Event) -> None:
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=5)
        return
    except asyncio.TimeoutError:
        pass

    while not stop_event.is_set():
        try:
            for source in repo.list_sources():
                if not source["enabled"] or not _is_due(source):
                    continue
                try:
                    await refresh_source(source["id"])
                except Exception:
                    logger.exception("Ошибка обновления источника %s", source["id"])
        except Exception:
            logger.exception("Ошибка планировщика")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=CHECK_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            continue
