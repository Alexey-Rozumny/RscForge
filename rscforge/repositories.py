from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

from .db import DEFAULT_SETTINGS, get_conn
from .parsers import ParsedEntry


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _chunks(items: Sequence[Any], size: int = 500) -> Iterable[Sequence[Any]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]


def _row(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------


def list_sources() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT s.*,
                   (SELECT COUNT(*) FROM entries e WHERE e.source_id = s.id) AS entry_count,
                   (SELECT COUNT(*) FROM entries e
                     WHERE e.source_id = s.id AND e.enabled = 1) AS enabled_count
            FROM sources s
            ORDER BY s.id
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_source(source_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT s.*,
                   (SELECT COUNT(*) FROM entries e WHERE e.source_id = s.id) AS entry_count,
                   (SELECT COUNT(*) FROM entries e
                     WHERE e.source_id = s.id AND e.enabled = 1) AS enabled_count
            FROM sources s
            WHERE s.id = ?
            """,
            (source_id,),
        ).fetchone()
    return _row(row)


def create_source(
    *,
    name: str,
    kind: str,
    url: str | None = None,
    stored_path: str | None = None,
    refresh_interval_minutes: int = 60,
    enabled: bool = True,
) -> dict:
    with get_conn() as conn:
        cursor = conn.execute(
            """
            INSERT INTO sources
                (name, kind, url, stored_path, enabled, refresh_interval_minutes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                kind,
                url,
                stored_path,
                int(enabled),
                refresh_interval_minutes,
                utcnow(),
            ),
        )
        source_id = int(cursor.lastrowid)
    result = get_source(source_id)
    assert result is not None
    return result


def update_source(source_id: int, fields: dict[str, Any]) -> dict | None:
    allowed = {"name", "url", "refresh_interval_minutes", "enabled"}
    updates = {key: value for key, value in fields.items() if key in allowed}
    if "enabled" in updates:
        updates["enabled"] = int(bool(updates["enabled"]))
    if updates:
        assignments = ", ".join(f"{key} = ?" for key in updates)
        with get_conn() as conn:
            conn.execute(
                f"UPDATE sources SET {assignments} WHERE id = ?",
                (*updates.values(), source_id),
            )
    return get_source(source_id)


def delete_source(source_id: int) -> bool:
    with get_conn() as conn:
        cursor = conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
    return cursor.rowcount > 0


def record_fetch(source_id: int, *, status: str | None, error: str | None) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE sources
               SET last_fetched_at = ?, last_status = ?, last_error = ?
             WHERE id = ?
            """,
            (utcnow(), status, error, source_id),
        )


# ---------------------------------------------------------------------------
# Entries
# ---------------------------------------------------------------------------


def list_entries(
    *,
    search: str | None = None,
    kind: str | None = None,
    source: str | None = None,
    enabled: bool | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict], int]:
    where: list[str] = []
    params: list[Any] = []

    if search:
        where.append("(e.normalized LIKE ? OR COALESCE(e.comment, '') LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    if kind in {"domain", "ip", "cidr"}:
        where.append("e.kind = ?")
        params.append(kind)
    if source == "manual":
        where.append("e.source_id IS NULL")
    elif source:
        try:
            source_id = int(source)
        except (TypeError, ValueError):
            return [], 0
        where.append("e.source_id = ?")
        params.append(source_id)
    if enabled is not None:
        where.append("e.enabled = ?")
        params.append(int(enabled))

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    with get_conn() as conn:
        total = int(
            conn.execute(
                f"SELECT COUNT(*) FROM entries e {where_sql}", params
            ).fetchone()[0]
        )
        rows = conn.execute(
            f"""
            SELECT e.*, s.name AS source_name
              FROM entries e
              LEFT JOIN sources s ON s.id = e.source_id
              {where_sql}
             ORDER BY e.kind, e.normalized
             LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()
    return [dict(row) for row in rows], total


def get_entry(entry_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT e.*, s.name AS source_name
              FROM entries e
              LEFT JOIN sources s ON s.id = e.source_id
             WHERE e.id = ?
            """,
            (entry_id,),
        ).fetchone()
    return _row(row)


def create_entry(
    *,
    source_id: int | None,
    parsed: ParsedEntry,
    comment: str | None = None,
    enabled: bool = True,
) -> dict:
    try:
        with get_conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO entries
                    (source_id, value, normalized, kind, enabled, comment, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    parsed.value,
                    parsed.normalized,
                    parsed.kind,
                    int(enabled),
                    comment,
                    utcnow(),
                ),
            )
            entry_id = int(cursor.lastrowid)
    except sqlite3.IntegrityError as exc:
        raise ValueError("Такая запись уже существует") from exc

    result = get_entry(entry_id)
    assert result is not None
    return result


def update_entry(entry_id: int, fields: dict[str, Any]) -> dict | None:
    allowed = {"value", "normalized", "kind", "comment", "enabled"}
    updates = {key: value for key, value in fields.items() if key in allowed}
    if "enabled" in updates:
        updates["enabled"] = int(bool(updates["enabled"]))
    if updates:
        assignments = ", ".join(f"{key} = ?" for key in updates)
        try:
            with get_conn() as conn:
                conn.execute(
                    f"UPDATE entries SET {assignments} WHERE id = ?",
                    (*updates.values(), entry_id),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Такая запись уже существует") from exc
    return get_entry(entry_id)


def delete_entry(entry_id: int) -> bool:
    with get_conn() as conn:
        cursor = conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
    return cursor.rowcount > 0


def bulk_entries(ids: Sequence[int], action: str) -> int:
    if not ids:
        return 0
    changed = 0
    with get_conn() as conn:
        for chunk in _chunks(list(ids)):
            placeholders = ",".join("?" for _ in chunk)
            if action == "delete":
                cursor = conn.execute(
                    f"DELETE FROM entries WHERE id IN ({placeholders})", chunk
                )
            else:
                cursor = conn.execute(
                    f"UPDATE entries SET enabled = ? WHERE id IN ({placeholders})",
                    (1 if action == "enable" else 0, *chunk),
                )
            changed += cursor.rowcount
    return changed


def entry_stats() -> dict:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS total,
                   COALESCE(SUM(enabled), 0) AS enabled,
                   COALESCE(SUM(CASE WHEN kind = 'domain' THEN 1 ELSE 0 END), 0) AS domains,
                   COALESCE(SUM(CASE WHEN kind IN ('ip', 'cidr') THEN 1 ELSE 0 END), 0) AS ip_entries
              FROM entries
            """
        ).fetchone()
    stats = dict(row)
    stats["disabled"] = stats["total"] - stats["enabled"]
    return stats


def replace_source_entries(source_id: int, entries: Sequence[ParsedEntry]) -> None:
    """Sync entries of an external source: keep edits, add new, drop stale."""
    new_map = {entry.normalized: entry for entry in entries}
    with get_conn() as conn:
        existing = {
            row["normalized"]: int(row["id"])
            for row in conn.execute(
                "SELECT id, normalized FROM entries WHERE source_id = ?", (source_id,)
            ).fetchall()
        }

        stale = [entry_id for norm, entry_id in existing.items() if norm not in new_map]
        for chunk in _chunks(stale):
            placeholders = ",".join("?" for _ in chunk)
            conn.execute(f"DELETE FROM entries WHERE id IN ({placeholders})", chunk)

        to_insert = [
            (
                source_id,
                entry.value,
                entry.normalized,
                entry.kind,
                1,
                entry.comment,
                utcnow(),
            )
            for norm, entry in new_map.items()
            if norm not in existing
        ]
        conn.executemany(
            """
            INSERT OR IGNORE INTO entries
                (source_id, value, normalized, kind, enabled, comment, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            to_insert,
        )


def export_entries() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT e.id, e.normalized, e.kind, e.comment, s.name AS source_name
              FROM entries e
              LEFT JOIN sources s ON s.id = e.source_id
             WHERE e.enabled = 1
            """
        ).fetchall()
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def get_settings() -> dict[str, str]:
    with get_conn() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    values = dict(DEFAULT_SETTINGS)
    values.update({row["key"]: row["value"] for row in rows})
    return values


def set_settings(values: dict[str, str]) -> dict[str, str]:
    updates = {key: value for key, value in values.items() if key in DEFAULT_SETTINGS}
    if updates:
        with get_conn() as conn:
            conn.executemany(
                """
                INSERT INTO settings(key, value) VALUES(?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                updates.items(),
            )
    return get_settings()
