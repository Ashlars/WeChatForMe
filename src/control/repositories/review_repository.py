from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from src.core.context import ContextManager


class ReviewRepository:
    def __init__(self, context: ContextManager) -> None:
        self._conn = context._conn

    def create_item(
        self,
        *,
        review_type: str,
        target_type: str,
        target_id: str,
        proposed_payload: dict[str, Any],
        analysis_run_id: int | None = None,
        rationale: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = datetime.now().isoformat()
        cursor = self._conn.execute(
            """INSERT INTO review_items
               (review_type, target_type, target_id, analysis_run_id,
                proposed_payload_json, rationale_json, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (
                review_type, target_type, target_id, analysis_run_id,
                json.dumps(proposed_payload, ensure_ascii=False),
                json.dumps(rationale, ensure_ascii=False) if rationale else None,
                now,
            ),
        )
        self._conn.commit()
        return self.get_item(cursor.lastrowid)

    def get_item(self, item_id: int) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM review_items WHERE id = ?", (item_id,)
        ).fetchone()
        if not row:
            return None
        return dict(row)

    def list_items(
        self, *, page: int = 1, page_size: int = 20,
        status: str | None = None, target_type: str | None = None,
        review_type: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        where_clauses = []
        params: list[Any] = []
        if status:
            where_clauses.append("status = ?")
            params.append(status)
        if target_type:
            where_clauses.append("target_type = ?")
            params.append(target_type)
        if review_type:
            where_clauses.append("review_type = ?")
            params.append(review_type)

        where = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        total = self._conn.execute(
            f"SELECT COUNT(*) AS count FROM review_items {where}", params
        ).fetchone()["count"]

        rows = self._conn.execute(
            f"SELECT * FROM review_items {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [page_size, (page - 1) * page_size],
        ).fetchall()

        return [dict(r) for r in rows], total

    def mark_applied(self, item_id: int, *, edited_payload: dict | None = None) -> None:
        row = self._conn.execute(
            "SELECT status FROM review_items WHERE id = ?", (item_id,)
        ).fetchone()
        if not row or row["status"] != "pending":
            raise ValueError(f"Review item {item_id} is not pending")

        now = datetime.now().isoformat()
        edited_json = json.dumps(edited_payload, ensure_ascii=False) if edited_payload else None
        self._conn.execute(
            """UPDATE review_items
               SET status = 'applied', reviewed_at = ?, applied_at = ?, edited_payload_json = ?
               WHERE id = ?""",
            (now, now, edited_json, item_id),
        )
        self._conn.commit()

    def mark_rejected(self, item_id: int) -> None:
        row = self._conn.execute(
            "SELECT status FROM review_items WHERE id = ?", (item_id,)
        ).fetchone()
        if not row or row["status"] != "pending":
            raise ValueError(f"Review item {item_id} is not pending")

        self._conn.execute(
            "UPDATE review_items SET status = 'rejected', reviewed_at = ? WHERE id = ?",
            (datetime.now().isoformat(), item_id),
        )
        self._conn.commit()

    def increment_error(self, item_id: int, error: str) -> None:
        self._conn.execute(
            """UPDATE review_items
               SET apply_attempts = apply_attempts + 1, last_error = ?
               WHERE id = ?""",
            (error, item_id),
        )
        self._conn.commit()

    def count_pending(self) -> int:
        return self._conn.execute(
            "SELECT COUNT(*) AS count FROM review_items WHERE status = 'pending'"
        ).fetchone()["count"]
