from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


class RefStore:
    def __init__(self, db_path: Path, legacy_json_path: Path):
        self.db_path = db_path
        self.legacy_json_path = legacy_json_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self.migrate_legacy_json()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS refs (
                    name TEXT PRIMARY KEY,
                    media_id TEXT NOT NULL,
                    file_path TEXT,
                    project_id TEXT,
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    note TEXT NOT NULL DEFAULT '',
                    raw_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_refs_media_id ON refs(media_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_refs_project_id ON refs(project_id)")

    def migrate_legacy_json(self) -> None:
        if not self.legacy_json_path.exists():
            return
        try:
            data = json.loads(self.legacy_json_path.read_text(encoding="utf-8-sig"))
        except Exception:
            return
        if not isinstance(data, dict):
            return
        for name, record in data.items():
            if not isinstance(record, dict) or not record.get("media_id"):
                continue
            existing = self.get(name)
            if existing:
                continue
            self.upsert(
                name=name,
                media_id=record["media_id"],
                file_path=record.get("file_path", ""),
                project_id=record.get("project_id", ""),
                raw=record.get("raw"),
                tags=record.get("tags") or [],
                note=record.get("note", ""),
                sync_legacy=False,
            )

    def upsert(
        self,
        *,
        name: str,
        media_id: str,
        file_path: str = "",
        project_id: str = "",
        raw: Any = None,
        tags: list[str] | None = None,
        note: str = "",
        sync_legacy: bool = True,
    ) -> dict[str, Any]:
        now = datetime.now().isoformat(timespec="seconds")
        tags = sorted({tag.strip() for tag in (tags or []) if tag and tag.strip()})
        existing = self.get(name)
        created_at = existing["created_at"] if existing else now
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO refs (
                    name, media_id, file_path, project_id, tags_json, note,
                    raw_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    media_id = excluded.media_id,
                    file_path = excluded.file_path,
                    project_id = excluded.project_id,
                    tags_json = excluded.tags_json,
                    note = excluded.note,
                    raw_json = excluded.raw_json,
                    updated_at = excluded.updated_at
                """,
                (
                    name,
                    media_id,
                    file_path,
                    project_id,
                    json.dumps(tags, ensure_ascii=False),
                    note,
                    json.dumps(raw, ensure_ascii=False) if raw is not None else None,
                    created_at,
                    now,
                ),
            )
        if sync_legacy:
            self.export_legacy_json()
        return self.get(name) or {}

    def get(self, name: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM refs WHERE name = ?", (name,)).fetchone()
        return self._row_to_dict(row) if row else None

    def list(self, *, search: str | None = None, tag: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM refs ORDER BY updated_at DESC, name ASC").fetchall()
        records = [self._row_to_dict(row) for row in rows]
        if search:
            needle = search.lower()
            records = [
                record
                for record in records
                if needle in record["name"].lower()
                or needle in record["media_id"].lower()
                or needle in record.get("file_path", "").lower()
                or needle in record.get("note", "").lower()
            ]
        if tag:
            records = [record for record in records if tag in record.get("tags", [])]
        return records

    def delete(self, name: str) -> bool:
        with self._connect() as conn:
            result = conn.execute("DELETE FROM refs WHERE name = ?", (name,))
        deleted = result.rowcount > 0
        if deleted:
            self.export_legacy_json()
        return deleted

    def resolve(self, value: str) -> str:
        record = self.get(value)
        return record["media_id"] if record else value

    def export_legacy_json(self) -> None:
        data = {
            record["name"]: {
                "media_id": record["media_id"],
                "file_path": record.get("file_path", ""),
                "project_id": record.get("project_id", ""),
                "tags": record.get("tags", []),
                "note": record.get("note", ""),
                "uploaded_at": record.get("created_at", ""),
                "updated_at": record.get("updated_at", ""),
                "raw": record.get("raw"),
            }
            for record in self.list()
        }
        self.legacy_json_path.parent.mkdir(parents=True, exist_ok=True)
        self.legacy_json_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        raw_json = row["raw_json"]
        tags_json = row["tags_json"] or "[]"
        try:
            raw = json.loads(raw_json) if raw_json else None
        except Exception:
            raw = None
        try:
            tags = json.loads(tags_json)
        except Exception:
            tags = []
        return {
            "name": row["name"],
            "media_id": row["media_id"],
            "file_path": row["file_path"] or "",
            "project_id": row["project_id"] or "",
            "tags": tags,
            "note": row["note"] or "",
            "raw": raw,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
