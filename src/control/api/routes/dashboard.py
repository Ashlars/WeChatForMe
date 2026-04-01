from __future__ import annotations

from fastapi import APIRouter, Request


router = APIRouter()


@router.get("/summary")
def get_dashboard_summary(request: Request) -> dict:
    conn = request.app.state.context._conn

    whitelist_count = conn.execute(
        "SELECT COUNT(*) AS c FROM contacts WHERE is_whitelist = 1"
    ).fetchone()["c"]

    active_group_count = conn.execute(
        "SELECT COUNT(*) AS c FROM groups WHERE is_active = 1"
    ).fetchone()["c"]

    pending_review_count = conn.execute(
        "SELECT COUNT(*) AS c FROM review_items WHERE status = 'pending'"
    ).fetchone()["c"]

    analysis_success_24h = conn.execute(
        "SELECT COUNT(*) AS c FROM analysis_runs WHERE status = 'succeeded' AND finished_at > datetime('now', '-24 hours')"
    ).fetchone()["c"]

    analysis_failed_24h = conn.execute(
        "SELECT COUNT(*) AS c FROM analysis_runs WHERE status = 'failed' AND finished_at > datetime('now', '-24 hours')"
    ).fetchone()["c"]

    return {
        "runtime_status": "running",
        "whitelist_count": whitelist_count,
        "active_group_count": active_group_count,
        "pending_review_count": pending_review_count,
        "analysis_success_24h": analysis_success_24h,
        "analysis_failed_24h": analysis_failed_24h,
    }
