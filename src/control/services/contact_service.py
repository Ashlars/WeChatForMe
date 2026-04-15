from __future__ import annotations

from src.control.schemas.api import ContactPatch
from src.core.context import ContextManager
from src.models.schemas import Contact


class ContactService:
    def __init__(self, context: ContextManager) -> None:
        self._context = context
        self._conn = context._conn

    def list_contacts(self, page: int = 1, page_size: int = 20) -> tuple[list[dict], int]:
        rows = self._conn.execute(
            """SELECT c.*, p.enabled AS pro_enabled, p.topic AS pro_topic
               FROM contacts c
               LEFT JOIN proactive_chats p ON c.wxid = p.id
               ORDER BY c.is_whitelist DESC, c.created_at ASC
               LIMIT ? OFFSET ?""",
            (page_size, (page - 1) * page_size),
        ).fetchall()
        total = self._conn.execute("SELECT COUNT(*) AS count FROM contacts").fetchone()["count"]
        items = [
            {
                "wxid": row["wxid"],
                "nickname": row["nickname"],
                "remark": row["remark"],
                "relationship": row["relationship"],
                "is_whitelist": bool(row["is_whitelist"]),
                "is_paused": bool(row["is_paused"]),
                "proactive_enabled": bool(row["pro_enabled"]) if row["pro_enabled"] else False,
                "proactive_topic": row["pro_topic"],
            }
            for row in rows
        ]
        return items, total

    def update_contact(self, wxid: str, patch: ContactPatch) -> Contact:
        contact = self._context.get_contact(wxid)
        if not contact:
            raise KeyError(wxid)

        changes = patch.model_dump(exclude_none=True)
        for key, value in changes.items():
            setattr(contact, key, value)
        self._context.save_contact(contact)

        # Sync nickname to all group_members entries for this wxid
        if "nickname" in changes:
            self._conn.execute(
                "UPDATE group_members SET nickname = ? WHERE wxid = ?",
                (changes["nickname"], wxid),
            )
            self._conn.commit()

        return self._context.get_contact(wxid) or contact
