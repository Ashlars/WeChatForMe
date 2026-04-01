from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel


router = APIRouter()


class ProactiveChatConfig(BaseModel):
    chat_type: str  # "group" or "private"
    chat_name: str | None = None
    enabled: bool = False
    interval_minutes: int = 5
    topic: str = ""


@router.get("")
def list_proactive_chats(request: Request) -> list[dict]:
    conn = request.app.state.context._conn
    rows = conn.execute(
        "SELECT * FROM proactive_chats ORDER BY enabled DESC, created_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


@router.get("/{chat_id:path}")
def get_proactive_chat(chat_id: str, request: Request) -> dict:
    conn = request.app.state.context._conn
    row = conn.execute(
        "SELECT * FROM proactive_chats WHERE id = ?", (chat_id,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="not_found")
    return dict(row)


@router.put("/{chat_id:path}")
def upsert_proactive_chat(chat_id: str, body: ProactiveChatConfig, request: Request) -> dict:
    conn = request.app.state.context._conn
    from datetime import datetime
    conn.execute(
        """INSERT OR REPLACE INTO proactive_chats
           (id, chat_type, chat_name, enabled, interval_minutes, topic, created_at)
           VALUES (?, ?, ?, ?, ?, ?, COALESCE(
               (SELECT created_at FROM proactive_chats WHERE id = ?),
               ?
           ))""",
        (
            chat_id, body.chat_type, body.chat_name,
            body.enabled, body.interval_minutes, body.topic,
            chat_id, datetime.now().isoformat(),
        ),
    )
    conn.commit()
    return dict(conn.execute(
        "SELECT * FROM proactive_chats WHERE id = ?", (chat_id,)
    ).fetchone())


@router.delete("/{chat_id:path}")
def delete_proactive_chat(chat_id: str, request: Request) -> dict:
    conn = request.app.state.context._conn
    conn.execute("DELETE FROM proactive_chats WHERE id = ?", (chat_id,))
    conn.commit()
    return {"deleted": True}
