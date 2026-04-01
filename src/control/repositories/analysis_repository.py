from __future__ import annotations

from datetime import datetime
from typing import Any

from src.core.context import ContextManager


class AnalysisRepository:
    def __init__(self, context: ContextManager) -> None:
        self._conn = context._conn

    def create_run(
        self, *, target_type: str, target_id: str, trigger_type: str,
    ) -> dict[str, Any]:
        now = datetime.now().isoformat()
        cursor = self._conn.execute(
            """INSERT INTO analysis_runs (target_type, target_id, trigger_type, status, created_at)
               VALUES (?, ?, ?, 'queued', ?)""",
            (target_type, target_id, trigger_type, now),
        )
        self._conn.commit()
        return self.get_run(cursor.lastrowid)

    def get_run(self, run_id: int) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM analysis_runs WHERE id = ?", (run_id,)
        ).fetchone()
        if not row:
            return None
        return dict(row)

    def list_runs(
        self, *, page: int = 1, page_size: int = 20,
        target_type: str | None = None, status: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        where_clauses = []
        params: list[Any] = []
        if target_type:
            where_clauses.append("target_type = ?")
            params.append(target_type)
        if status:
            where_clauses.append("status = ?")
            params.append(status)

        where = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        total = self._conn.execute(
            f"SELECT COUNT(*) AS count FROM analysis_runs {where}", params
        ).fetchone()["count"]

        rows = self._conn.execute(
            f"SELECT * FROM analysis_runs {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [page_size, (page - 1) * page_size],
        ).fetchall()

        return [dict(r) for r in rows], total

    def mark_running(self, run_id: int) -> None:
        self._conn.execute(
            "UPDATE analysis_runs SET status = 'running', started_at = ? WHERE id = ?",
            (datetime.now().isoformat(), run_id),
        )
        self._conn.commit()

    def mark_succeeded(
        self, run_id: int, *, summary: str, persona_json: str, suggestions_json: str,
    ) -> None:
        self._conn.execute(
            """UPDATE analysis_runs
               SET status = 'succeeded', summary = ?, persona_json = ?,
                   suggestions_json = ?, finished_at = ?
               WHERE id = ?""",
            (summary, persona_json, suggestions_json, datetime.now().isoformat(), run_id),
        )
        self._conn.commit()

    def mark_failed(self, run_id: int, *, error_message: str) -> None:
        self._conn.execute(
            """UPDATE analysis_runs
               SET status = 'failed', error_message = ?, finished_at = ?
               WHERE id = ?""",
            (error_message, datetime.now().isoformat(), run_id),
        )
        self._conn.commit()

    def recover_stale(self) -> int:
        cursor = self._conn.execute(
            """UPDATE analysis_runs SET status = 'failed', error_message = 'worker_restarted', finished_at = ?
               WHERE status IN ('running', 'queued')""",
            (datetime.now().isoformat(),),
        )
        self._conn.commit()
        return cursor.rowcount
