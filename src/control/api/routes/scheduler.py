from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel


class AnalysisPolicyUpdate(BaseModel):
    enabled: bool | None = None
    cron_expr: str | None = None
    max_targets_per_run: int | None = None
    contacts_enabled: bool | None = None
    groups_enabled: bool | None = None
    min_hours_since_last_analysis: int | None = None
    selection_strategy: str | None = None
    overlap_policy: str | None = None


router = APIRouter()


def _ensure_policy_row(conn) -> None:
    row = conn.execute("SELECT id FROM analysis_policies WHERE id = 1").fetchone()
    if not row:
        conn.execute(
            """INSERT INTO analysis_policies
               (id, enabled, cron_expr, max_targets_per_run, contacts_enabled, groups_enabled,
                min_hours_since_last_analysis, selection_strategy, overlap_policy, updated_at)
               VALUES (1, 0, '0 */6 * * *', 20, 1, 1, 24, 'recently_active_first', 'skip', ?)""",
            (datetime.now().isoformat(),),
        )
        conn.commit()


@router.get("/analysis-policy")
def get_analysis_policy(request: Request) -> dict:
    conn = request.app.state.context._conn
    _ensure_policy_row(conn)
    row = conn.execute("SELECT * FROM analysis_policies WHERE id = 1").fetchone()
    return dict(row)


@router.put("/analysis-policy")
def update_analysis_policy(body: AnalysisPolicyUpdate, request: Request) -> dict:
    conn = request.app.state.context._conn
    _ensure_policy_row(conn)

    changes = body.model_dump(exclude_none=True)
    if changes:
        changes["updated_at"] = datetime.now().isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in changes)
        conn.execute(
            f"UPDATE analysis_policies SET {set_clause} WHERE id = 1",
            list(changes.values()),
        )
        conn.commit()

    row = conn.execute("SELECT * FROM analysis_policies WHERE id = 1").fetchone()
    return dict(row)
