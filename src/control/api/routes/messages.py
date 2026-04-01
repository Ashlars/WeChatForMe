from __future__ import annotations

from fastapi import APIRouter, Request

from src.control.schemas.api import PaginatedResponse


router = APIRouter()


@router.get("", response_model=PaginatedResponse)
def list_messages(
    request: Request,
    page: int = 1,
    page_size: int = 50,
    contact_id: str | None = None,
    group_id: str | None = None,
    direction: str | None = None,
) -> PaginatedResponse:
    conn = request.app.state.context._conn

    where_clauses = []
    params: list = []
    if contact_id:
        where_clauses.append("contact_id = ?")
        params.append(contact_id)
    if group_id:
        where_clauses.append("group_id = ?")
        params.append(group_id)
    if direction:
        where_clauses.append("direction = ?")
        params.append(direction)

    where = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    total = conn.execute(
        f"SELECT COUNT(*) AS c FROM messages {where}", params
    ).fetchone()["c"]

    rows = conn.execute(
        f"SELECT * FROM messages {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params + [page_size, (page - 1) * page_size],
    ).fetchall()

    items = [dict(r) for r in rows]
    return PaginatedResponse(items=items, page=page, page_size=page_size, total=total)


@router.get("/conversations")
def list_conversations(request: Request) -> dict:
    """List all unique conversations (contacts/groups) with latest message."""
    conn = request.app.state.context._conn

    # Get private chats
    private = conn.execute("""
        SELECT contact_id, MAX(created_at) as last_msg_at, COUNT(*) as msg_count,
               (SELECT content FROM messages m2 WHERE m2.contact_id = m.contact_id AND m2.group_id IS NULL ORDER BY created_at DESC LIMIT 1) as last_content
        FROM messages m
        WHERE group_id IS NULL
        GROUP BY contact_id
        ORDER BY last_msg_at DESC
        LIMIT 50
    """).fetchall()

    # Get group chats
    groups = conn.execute("""
        SELECT group_id, MAX(created_at) as last_msg_at, COUNT(*) as msg_count,
               (SELECT content FROM messages m2 WHERE m2.group_id = m.group_id ORDER BY created_at DESC LIMIT 1) as last_content
        FROM messages m
        WHERE group_id IS NOT NULL
        GROUP BY group_id
        ORDER BY last_msg_at DESC
        LIMIT 50
    """).fetchall()

    # Resolve names
    ctx = request.app.state.context
    private_items = []
    for r in private:
        contact = ctx.get_contact(r["contact_id"])
        private_items.append({
            "type": "private",
            "id": r["contact_id"],
            "name": (contact.remark or contact.nickname or r["contact_id"]) if contact else r["contact_id"],
            "last_msg_at": r["last_msg_at"],
            "msg_count": r["msg_count"],
            "last_content": r["last_content"],
        })

    group_items = []
    for r in groups:
        group = ctx.get_group(r["group_id"])
        group_items.append({
            "type": "group",
            "id": r["group_id"],
            "name": (group.group_name or r["group_id"]) if group else r["group_id"],
            "last_msg_at": r["last_msg_at"],
            "msg_count": r["msg_count"],
            "last_content": r["last_content"],
        })

    return {"private": private_items, "groups": group_items}
