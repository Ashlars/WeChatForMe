from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger

from src.control.repositories.event_repository import EventRepository
from src.control.repositories.review_repository import ReviewRepository
from src.control.services.rule_service import RuleService
from src.core.context import ContextManager


class ReviewService:
    def __init__(self, context: ContextManager, *, style_dir: str | Path) -> None:
        self._context = context
        self._review_repo = ReviewRepository(context)
        self._rule_service = RuleService(context, style_dir)
        self._event_repo = EventRepository(context)

    def approve(self, item_id: int) -> dict[str, Any]:
        item = self._review_repo.get_item(item_id)
        if not item:
            raise KeyError(f"Review item {item_id} not found")
        if item["status"] != "pending":
            raise ValueError(f"Review item {item_id} is not pending")

        payload = json.loads(item["proposed_payload_json"])
        review_type = item["review_type"]

        try:
            self._apply(review_type, item["target_type"], item["target_id"], payload)
            self._review_repo.mark_applied(item_id)
            self._event_repo.log(
                "review_applied", "info",
                f"Review {item_id} ({review_type}) applied for {item['target_type']}/{item['target_id']}",
            )
        except Exception as e:
            self._review_repo.increment_error(item_id, str(e))
            raise

        return self._review_repo.get_item(item_id)

    def reject(self, item_id: int) -> dict[str, Any]:
        item = self._review_repo.get_item(item_id)
        if not item:
            raise KeyError(f"Review item {item_id} not found")

        self._review_repo.mark_rejected(item_id)
        self._event_repo.log(
            "review_rejected", "info", f"Review {item_id} rejected",
        )
        return self._review_repo.get_item(item_id)

    def apply_edited(self, item_id: int, edited_payload: dict[str, Any]) -> dict[str, Any]:
        item = self._review_repo.get_item(item_id)
        if not item:
            raise KeyError(f"Review item {item_id} not found")
        if item["status"] != "pending":
            raise ValueError(f"Review item {item_id} is not pending")

        review_type = item["review_type"]

        try:
            self._apply(review_type, item["target_type"], item["target_id"], edited_payload)
            self._review_repo.mark_applied(item_id, edited_payload=edited_payload)
            self._event_repo.log(
                "review_applied_edited", "info",
                f"Review {item_id} ({review_type}) applied with edits",
            )
        except Exception as e:
            self._review_repo.increment_error(item_id, str(e))
            raise

        return self._review_repo.get_item(item_id)

    def _apply(
        self, review_type: str, target_type: str, target_id: str, payload: dict,
    ) -> None:
        if review_type == "rule_change":
            self._apply_rule_change(target_type, target_id, payload)
        elif review_type == "contact_profile_change":
            self._apply_profile_change("contacts", target_id, payload)
        elif review_type == "group_profile_change":
            self._apply_profile_change("groups", target_id, payload)
        elif review_type == "contact_state_change":
            self._apply_state_change(target_id, payload)
        else:
            raise ValueError(f"Unknown review_type: {review_type}")

    def _apply_rule_change(self, target_type: str, target_id: str, payload: dict) -> None:
        scope_type = "contact" if target_type == "contact" else "group"
        current = self._rule_service.get_rule(scope_type, target_id)
        document = current["document"] if current else {"metadata": {}, "chat_rules": {}}

        path = payload.get("path", "")
        value = payload.get("value")
        if path.startswith("chat_rules."):
            field = path.split(".", 1)[1]
            document["chat_rules"][field] = value
        elif path.startswith("metadata."):
            field = path.split(".", 1)[1]
            document["metadata"][field] = value

        self._rule_service.upsert_rule(
            scope_type=scope_type,
            scope_id=target_id,
            document=document,
            source="analysis_applied",
        )

    def _apply_profile_change(self, table: str, target_id: str, payload: dict) -> None:
        field = payload.get("field")
        value = payload.get("value")

        allowed_contact = {"relationship", "persona_summary", "style_summary", "interaction_style_summary"}
        allowed_group = {"group_profile", "reply_strategy"}
        allowed = allowed_contact if table == "contacts" else allowed_group

        if field not in allowed:
            raise ValueError(f"Field {field} not allowed for {table}")

        id_col = "wxid" if table == "contacts" else "group_id"
        self._context._conn.execute(
            f"UPDATE {table} SET {field} = ? WHERE {id_col} = ?",
            (value, target_id),
        )
        self._context._conn.commit()

    def _apply_state_change(self, target_id: str, payload: dict) -> None:
        field = payload.get("field")
        value = payload.get("value")

        if field not in ("is_whitelist", "is_paused"):
            raise ValueError(f"State field {field} not allowed")

        self._context._conn.execute(
            f"UPDATE contacts SET {field} = ? WHERE wxid = ?",
            (value, target_id),
        )
        self._context._conn.commit()
