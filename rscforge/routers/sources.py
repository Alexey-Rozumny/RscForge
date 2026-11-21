from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from .. import repositories as repo
from ..config import settings
from ..schemas import SourceCreate, SourceUpdate
from ..services import refresh_all, refresh_source

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("")
def list_sources() -> list[dict]:
    return repo.list_sources()


@router.post("", status_code=201)
async def create_source(payload: SourceCreate) -> dict:
    source = repo.create_source(
        name=payload.name.strip(),
        kind="url",
        url=payload.url.strip(),
        refresh_interval_minutes=payload.refresh_interval_minutes,
        enabled=payload.enabled,
    )
    return await _refresh_and_return(source["id"])


@router.post("/upload", status_code=201)
async def upload_source(
    file: UploadFile = File(...),
    name: str | None = Form(None),
    refresh_interval_minutes: int = Form(60),
) -> dict:
    if not 5 <= refresh_interval_minutes <= 10080:
        raise HTTPException(
            status_code=422, detail="Интервал должен быть от 5 до 10080 минут"
        )

    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Файл больше лимита {settings.max_upload_bytes} байт",
        )
    if not data:
        raise HTTPException(status_code=400, detail="Файл пустой")

    suffix = Path(file.filename or "list.txt").suffix.lower()
    if not re.fullmatch(r"\.[a-z0-9]{1,8}", suffix):
        suffix = ".txt"

    stored_path = settings.uploads_dir / f"{uuid4().hex}{suffix}"
    stored_path.write_bytes(data)

    source_name = (name or file.filename or "Загруженный список").strip()[:100]
    source = repo.create_source(
        name=source_name,
        kind="file",
        stored_path=str(stored_path),
        refresh_interval_minutes=refresh_interval_minutes,
    )
    return await _refresh_and_return(source["id"])


@router.patch("/{source_id}")
def update_source(source_id: int, payload: SourceUpdate) -> dict:
    if repo.get_source(source_id) is None:
        raise HTTPException(status_code=404, detail="Источник не найден")
    fields = payload.model_dump(exclude_none=True)
    if "name" in fields:
        fields["name"] = fields["name"].strip()
    if "url" in fields:
        fields["url"] = fields["url"].strip()
    source = repo.update_source(source_id, fields)
    assert source is not None
    return source


@router.delete("/{source_id}", status_code=204)
def delete_source(source_id: int) -> Response:
    source = repo.get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Источник не найден")
    if source["kind"] == "file" and source.get("stored_path"):
        Path(source["stored_path"]).unlink(missing_ok=True)
    repo.delete_source(source_id)
    return Response(status_code=204)


@router.post("/{source_id}/refresh")
async def refresh_one(source_id: int) -> dict:
    if repo.get_source(source_id) is None:
        raise HTTPException(status_code=404, detail="Источник не найден")
    return await _refresh_and_return(source_id)


@router.post("/refresh-all")
async def refresh_everything() -> dict:
    return {"results": await refresh_all()}


async def _refresh_and_return(source_id: int) -> dict:
    error: str | None = None
    try:
        await refresh_source(source_id)
    except Exception as exc:
        error = str(exc)

    source = repo.get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Источник не найден")
    source["refresh_error"] = error
    return source
