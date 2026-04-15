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
            """SELECT g.*, p.enabled AS pro_enabled, p.topic AS pro_topic
               FROM groups g
               LEFT JOIN proactive_chats p ON g.group_id = p.id
               ORDER BY g.is_active DESC, g.created_at ASC
               LIMIT ? OFFSET ?""",
            (page_size, (page - 1) * page_size),
        ).fetchall()
        total = self._conn.execute("SELECT COUNT(*) AS count FROM groups").fetchone()["count"]
        items = []
        for row in rows:
            import json
            raw_kw = row["keywords"] or "[]"
            try:
                keywords = json.loads(raw_kw)
            except (json.JSONDecodeError, TypeError):
                keywords = []
            items.append({
                "group_id": row["group_id"],
                "group_name": row["group_name"],
                "is_active": bool(row["is_active"]),
                "trigger_mode": row["trigger_mode"],
                "keywords": keywords,
                "proactive_enabled": bool(row["pro_enabled"]) if row["pro_enabled"] else False,
                "proactive_topic": row["pro_topic"],
            })
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
