from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from .. import repositories as repo
from .. import resolver
from ..rsc import domain_targets, generate_rsc

router = APIRouter(tags=["export"])


async def _build() -> tuple[str, dict]:
    entries = repo.export_entries()
    values = repo.get_settings()
    targets = domain_targets(entries, values)
    resolved = await resolver.resolve_domains(targets)
    if targets and not any(resolved.values()):
        raise HTTPException(
            status_code=503,
            detail=(
                "DNS: не удалось разрешить ни одного домена. "
                "Экспорт остановлен, чтобы не очистить address-list."
            ),
        )
    return generate_rsc(entries, values, resolved)


@router.get("/api/export/preview")
async def preview() -> dict:
    content, stats = await _build()
    return {"content": content, "stats": stats}


async def _download_response() -> Response:
    content, _ = await _build()
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="rscforge.rsc"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/api/export/download", include_in_schema=False)
async def ui_download() -> Response:
    """Download for the web UI (normal Basic auth, no export token)."""
    return await _download_response()


@router.get("/export.rsc", include_in_schema=False)
async def download() -> Response:
    """MikroTik endpoint (export token or Basic auth)."""
    return await _download_response()
