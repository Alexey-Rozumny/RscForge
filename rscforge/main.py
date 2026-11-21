from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import __version__
from .auth import auth_middleware
from .db import init_db
from .routers import entries, export, pages, sources
from .routers import settings as settings_router
from .scheduler import scheduler_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    stop_event = asyncio.Event()
    scheduler_task = asyncio.create_task(
        scheduler_loop(stop_event), name="rscforge-scheduler"
    )
    app.state.stop_event = stop_event
    app.state.scheduler_task = scheduler_task
    logger.info("RscForge %s started", __version__)
    try:
        yield
    finally:
        stop_event.set()
        scheduler_task.cancel()
        with suppress(asyncio.CancelledError):
            await scheduler_task


app = FastAPI(title="RscForge", version=__version__, lifespan=lifespan)
app.middleware("http")(auth_middleware)

app.include_router(pages.router)
app.include_router(sources.router)
app.include_router(entries.router)
app.include_router(export.router)
app.include_router(settings_router.router)

app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).resolve().parent / "static"),
    name="static",
)
