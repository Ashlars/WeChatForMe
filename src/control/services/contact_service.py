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
            """SELECT * FROM contacts
               ORDER BY created_at ASC
               LIMIT ? OFFSET ?""",
            (page_size, (page - 1) * page_size),
        ).fetchall()
        total = self._conn.execute("SELECT COUNT(*) AS count FROM contacts").fetchone()["count"]
        items = []
        for row in rows:
            pro = self._conn.execute(
                "SELECT enabled, topic FROM proactive_chats WHERE id = ?",
                (row["wxid"],),
            ).fetchone()
            items.append({
                "wxid": row["wxid"],
                "nickname": row["nickname"],
                "remark": row["remark"],
                "relationship": row["relationship"],
                "is_whitelist": bool(row["is_whitelist"]),
                "is_paused": bool(row["is_paused"]),
                "proactive_enabled": bool(pro and pro["enabled"]) if pro else False,
                "proactive_topic": pro["topic"] if pro else None,
            })
        return items, total

    def update_contact(self, wxid: str, patch: ContactPatch) -> Contact:
        contact = self._context.get_contact(wxid)
        if not contact:
            raise KeyError(wxid)

        changes = patch.model_dump(exclude_none=True)
        for key, value in changes.items():
            setattr(contact, key, value)
        self._context.save_contact(contact)
        return self._context.get_contact(wxid) or contact
