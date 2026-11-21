from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response

from .. import repositories as repo
from ..rsc import generate_rsc

router = APIRouter(tags=["export"])


def _build() -> tuple[str, dict]:
    return generate_rsc(repo.export_entries(), repo.get_settings())


@router.get("/api/export/preview")
def preview() -> dict:
    content, stats = _build()
    return {"content": content, "stats": stats}


def _download_response() -> Response:
    content, _ = _build()
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="rscforge.rsc"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/api/export/download", include_in_schema=False)
def ui_download() -> Response:
    """Download for the web UI (normal Basic auth, no export token)."""
    return _download_response()


@router.get("/export.rsc", include_in_schema=False)
def download() -> Response:
    """MikroTik endpoint (export token or Basic auth)."""
    return _download_response()
