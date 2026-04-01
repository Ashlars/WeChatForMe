from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from src.core.context import ContextManager


class EventRepository:
    def __init__(self, context: ContextManager) -> None:
        self._conn = context._conn

    def log(
        self, event_type: str, level: str, message: str, *, payload: dict | None = None,
    ) -> None:
        self._conn.execute(
            """INSERT INTO runtime_events (event_type, level, message, payload_json, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                event_type, level, message,
                json.dumps(payload, ensure_ascii=False) if payload else None,
                datetime.now().isoformat(),
            ),
        )
        self._conn.commit()

    def list_events(
        self, *, page: int = 1, page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        total = self._conn.execute(
            "SELECT COUNT(*) AS count FROM runtime_events"
        ).fetchone()["count"]

        rows = self._conn.execute(
            "SELECT * FROM runtime_events ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (page_size, (page - 1) * page_size),
        ).fetchall()

        return [dict(r) for r in rows], total
