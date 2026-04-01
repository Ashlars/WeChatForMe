from __future__ import annotations

from src.control.schemas.api import GroupPatch
from src.core.context import ContextManager
from src.models.schemas import Group


class GroupService:
    def __init__(self, context: ContextManager) -> None:
        self._context = context
        self._conn = context._conn

    def list_groups(self, page: int = 1, page_size: int = 20) -> tuple[list[dict], int]:
        rows = self._conn.execute(
            """SELECT * FROM groups
               ORDER BY created_at ASC
               LIMIT ? OFFSET ?""",
            (page_size, (page - 1) * page_size),
        ).fetchall()
        total = self._conn.execute("SELECT COUNT(*) AS count FROM groups").fetchone()["count"]
        items = []
        for row in rows:
            group = self._context.get_group(row["group_id"])
            # Check proactive chat status
            pro = self._conn.execute(
                "SELECT enabled, topic, interval_minutes FROM proactive_chats WHERE id = ?",
                (row["group_id"],),
            ).fetchone()
            items.append(
                {
                    "group_id": row["group_id"],
                    "group_name": row["group_name"],
                    "is_active": bool(row["is_active"]),
                    "trigger_mode": row["trigger_mode"],
                    "keywords": group.keywords if group else [],
                    "proactive_enabled": bool(pro and pro["enabled"]) if pro else False,
                    "proactive_topic": pro["topic"] if pro else None,
                }
            )
        return items, total

    def update_group(self, group_id: str, patch: GroupPatch) -> Group:
        group = self._context.get_group(group_id)
        if not group:
            raise KeyError(group_id)

        changes = patch.model_dump(exclude_none=True)
        for key, value in changes.items():
            setattr(group, key, value)
        self._context.save_group(group)
        return self._context.get_group(group_id) or group
