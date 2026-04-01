from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from src.core.context import ContextManager


class RuleRepository:
    def __init__(self, context: ContextManager) -> None:
        self._context = context
        self._conn = context._conn

    def create_rule_version(
        self,
        *,
        scope_type: str,
        scope_id: str,
        source: str,
        document: dict[str, Any],
    ) -> dict[str, Any]:
        serialized = json.dumps(document, ensure_ascii=False, sort_keys=True)
        content_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        now = datetime.now().isoformat()

        row = self._conn.execute(
            """SELECT COALESCE(MAX(version), 0) AS max_version
               FROM rule_sets
               WHERE scope_type = ? AND scope_id = ?""",
            (scope_type, scope_id),
        ).fetchone()
        version = int(row["max_version"] or 0) + 1

        with self._conn:
            self._conn.execute(
                """UPDATE rule_sets
                   SET is_active = 0
                   WHERE scope_type = ? AND scope_id = ?""",
                (scope_type, scope_id),
            )
            cursor = self._conn.execute(
                """INSERT INTO rule_sets
                   (scope_type, scope_id, source, rules_json, content_hash,
                    version, is_active, sync_status, updated_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, 1, 'synced', ?, ?)""",
                (
                    scope_type,
                    scope_id,
                    source,
                    serialized,
                    content_hash,
                    version,
                    now,
                    now,
                ),
            )

        return {
            "id": cursor.lastrowid,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "source": source,
            "document": document,
            "content_hash": content_hash,
            "version": version,
            "is_active": True,
            "sync_status": "synced",
        }

    def get_active_rule(self, scope_type: str, scope_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            """SELECT * FROM rule_sets
               WHERE scope_type = ? AND scope_id = ? AND is_active = 1
               ORDER BY version DESC
               LIMIT 1""",
            (scope_type, scope_id),
        ).fetchone()
        if not row:
            return None

        return {
            "id": row["id"],
            "scope_type": row["scope_type"],
            "scope_id": row["scope_id"],
            "source": row["source"],
            "document": json.loads(row["rules_json"]),
            "content_hash": row["content_hash"],
            "version": row["version"],
            "is_active": bool(row["is_active"]),
            "sync_status": row["sync_status"],
        }
