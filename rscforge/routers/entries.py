from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from .. import repositories as repo
from ..parsers import parse_text, parse_value
from ..schemas import BulkEntries, EntryCreate, EntryUpdate

router = APIRouter(prefix="/api/entries", tags=["entries"])


@router.get("")
def list_entries(
    search: str | None = None,
    kind: str | None = None,
    source: str | None = None,
    enabled: bool | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict:
    items, total = repo.list_entries(
        search=search,
        kind=kind,
        source=source,
        enabled=enabled,
        limit=limit,
        offset=offset,
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/stats")
def stats() -> dict:
    return repo.entry_stats()


@router.post("", status_code=201)
def create_entries(payload: EntryCreate) -> dict:
    result = parse_text(payload.value)
    if not result.entries:
        raise HTTPException(
            status_code=400, detail="Не удалось распознать ни одной записи"
        )

    created: list[dict] = []
    duplicates = 0
    for parsed in result.entries:
        try:
            created.append(
                repo.create_entry(
                    source_id=None,
                    parsed=parsed,
                    comment=payload.comment,
                    enabled=payload.enabled,
                )
            )
        except ValueError:
            duplicates += 1

    return {
        "created": len(created),
        "duplicates": duplicates,
        "skipped": result.skipped,
        "items": created,
    }


@router.post("/bulk")
def bulk(payload: BulkEntries) -> dict:
    return {"changed": repo.bulk_entries(payload.ids, payload.action)}


@router.patch("/{entry_id}")
def update_entry(entry_id: int, payload: EntryUpdate) -> dict:
    if repo.get_entry(entry_id) is None:
        raise HTTPException(status_code=404, detail="Запись не найдена")

    fields = payload.model_dump(exclude_none=True)
    if "value" in fields:
        parsed = parse_value(fields["value"])
        if parsed is None:
            raise HTTPException(
                status_code=400, detail="Не удалось распознать запись"
            )
        fields.update(
            value=parsed.value, normalized=parsed.normalized, kind=parsed.kind
        )

    try:
        entry = repo.update_entry(entry_id, fields)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    assert entry is not None
    return entry


@router.delete("/{entry_id}", status_code=204)
def delete_entry(entry_id: int) -> Response:
    if not repo.delete_entry(entry_id):
        raise HTTPException(status_code=404, detail="Запись не найдена")
    return Response(status_code=204)
