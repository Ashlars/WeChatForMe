from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel


router = APIRouter()


class MemberPatch(BaseModel):
    # Group-level fields
    nickname: str | None = None
    role: str | None = None
    personality: str | None = None
    style_notes: str | None = None
    notes: str | None = None
    my_alias_for: str | None = None  # what I call this person in this group
    # Contact-level fields (synced to contacts table)
    relationship: str | None = None
    persona_summary: str | None = None
    contact_style_summary: str | None = None
    interaction_style_summary: str | None = None
    contact_my_alias_for: str | None = None  # what I call this person generally


def _merge_member_contact(conn, group_id: str, wxid: str) -> dict | None:
    """Fetch group member joined with contact data."""
    row = conn.execute(
        """SELECT
             gm.group_id, gm.wxid, gm.nickname, gm.role, gm.personality,
             gm.style_notes, gm.notes, gm.msg_count, gm.last_msg_at,
             gm.my_alias_for AS group_my_alias,
             c.remark AS contact_remark,
             c.relationship AS contact_relationship,
             c.persona_summary AS contact_persona,
             c.style_summary AS contact_style,
             c.interaction_style_summary AS contact_interaction,
             c.is_whitelist AS contact_is_whitelist,
             c.my_alias_for AS contact_my_alias
           FROM group_members gm
           LEFT JOIN contacts c ON gm.wxid = c.wxid
           WHERE gm.group_id = ? AND gm.wxid = ?""",
        (group_id, wxid),
    ).fetchone()
    return dict(row) if row else None


@router.get("/{group_id}/members")
def list_group_members(group_id: str, request: Request) -> list[dict]:
    conn = request.app.state.context._conn
    rows = conn.execute(
        """SELECT
             gm.group_id, gm.wxid, gm.nickname, gm.role, gm.personality,
             gm.style_notes, gm.notes, gm.msg_count, gm.last_msg_at,
             gm.my_alias_for AS group_my_alias,
             c.remark AS contact_remark,
             c.relationship AS contact_relationship,
             c.persona_summary AS contact_persona,
             c.style_summary AS contact_style,
             c.interaction_style_summary AS contact_interaction,
             c.is_whitelist AS contact_is_whitelist,
             c.my_alias_for AS contact_my_alias
           FROM group_members gm
           LEFT JOIN contacts c ON gm.wxid = c.wxid
           WHERE gm.group_id = ?
           ORDER BY gm.msg_count DESC""",
        (group_id,),
    ).fetchall()
    return [dict(r) for r in rows]


@router.patch("/{group_id}/members/{wxid}")
def update_group_member(group_id: str, wxid: str, body: MemberPatch, request: Request) -> dict:
    conn = request.app.state.context._conn
    row = conn.execute(
        "SELECT * FROM group_members WHERE group_id = ? AND wxid = ?",
        (group_id, wxid),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="member_not_found")

    changes = body.model_dump(exclude_none=True)

    # Split into group-level and contact-level updates
    group_fields = {"nickname", "role", "personality", "style_notes", "notes", "my_alias_for"}
    contact_fields = {
        "relationship": "relationship",
        "persona_summary": "persona_summary",
        "contact_style_summary": "style_summary",
        "interaction_style_summary": "interaction_style_summary",
        "contact_my_alias_for": "my_alias_for",
    }

    group_changes = {k: v for k, v in changes.items() if k in group_fields}
    contact_changes = {contact_fields[k]: v for k, v in changes.items() if k in contact_fields}

    ctx = request.app.state.context
    with ctx._lock:
        if group_changes:
            set_clause = ", ".join(f"{k} = ?" for k in group_changes)
            conn.execute(
                f"UPDATE group_members SET {set_clause} WHERE group_id = ? AND wxid = ?",
                list(group_changes.values()) + [group_id, wxid],
            )

        if contact_changes:
            contact_row = conn.execute("SELECT wxid FROM contacts WHERE wxid = ?", (wxid,)).fetchone()
            if contact_row:
                set_clause = ", ".join(f"{k} = ?" for k in contact_changes)
                conn.execute(
                    f"UPDATE contacts SET {set_clause} WHERE wxid = ?",
                    list(contact_changes.values()) + [wxid],
                )

        conn.commit()
    return _merge_member_contact(conn, group_id, wxid)
