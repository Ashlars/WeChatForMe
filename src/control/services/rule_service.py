from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from src.control.repositories.rule_repository import RuleRepository
from src.core.context import ContextManager


class RuleService:
    def __init__(self, context: ContextManager, style_dir: str | Path) -> None:
        self._context = context
        self._repository = RuleRepository(context)
        self._style_dir = Path(style_dir)

    def get_rule(self, scope_type: str, scope_id: str) -> dict[str, Any] | None:
        return self._repository.get_active_rule(scope_type, scope_id)

    def upsert_rule(
        self,
        *,
        scope_type: str,
        scope_id: str,
        document: dict[str, Any],
        source: str = "manual",
    ) -> dict[str, Any]:
        normalized = self._normalize_document(document)
        rule = self._repository.create_rule_version(
            scope_type=scope_type,
            scope_id=scope_id,
            source=source,
            document=normalized,
        )
        self._write_projection(scope_type, scope_id, normalized)
        return rule

    def _normalize_document(self, document: dict[str, Any]) -> dict[str, Any]:
        return {
            "metadata": document.get("metadata", {}),
            "chat_rules": document.get("chat_rules", {}),
        }

    def _write_projection(self, scope_type: str, scope_id: str, document: dict[str, Any]) -> None:
        target = self._resolve_target(scope_type, scope_id)
        target.parent.mkdir(parents=True, exist_ok=True)

        payload = dict(document.get("metadata", {}))
        payload["chat_rules"] = document.get("chat_rules", {})

        with target.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(payload, handle, allow_unicode=True, sort_keys=False)

    def _resolve_target(self, scope_type: str, scope_id: str) -> Path:
        if scope_type == "global":
            return self._style_dir / "default.yaml"
        if scope_type == "contact":
            return self._style_dir / "contacts" / f"{scope_id}.yaml"
        if scope_type == "group":
            return self._style_dir / "groups" / f"{scope_id}.yaml"
        raise ValueError(f"unsupported scope_type: {scope_type}")
