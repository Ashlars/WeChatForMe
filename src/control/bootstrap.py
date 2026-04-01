from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from src.control.repositories.rule_repository import RuleRepository
from src.core.context import ContextManager


def bootstrap_rules_if_empty(context: ContextManager, style_dir: str | Path) -> None:
    existing = context._conn.execute(
        "SELECT COUNT(*) AS count FROM rule_sets",
    ).fetchone()
    if existing and existing["count"]:
        return

    style_path = Path(style_dir)
    repo = RuleRepository(context)

    default_path = style_path / "default.yaml"
    if default_path.exists():
        repo.create_rule_version(
            scope_type="global",
            scope_id="__global__",
            source="manual",
            document=_normalise_style_document(_read_yaml(default_path)),
        )

    contacts_dir = style_path / "contacts"
    if contacts_dir.exists():
        for file_path in sorted(contacts_dir.glob("*.yaml")):
            raw = _read_yaml(file_path)
            scope_id = raw.get("wxid") or file_path.stem
            repo.create_rule_version(
                scope_type="contact",
                scope_id=scope_id,
                source="manual",
                document=_normalise_style_document(raw),
            )

    groups_dir = style_path / "groups"
    if groups_dir.exists():
        for file_path in sorted(groups_dir.glob("*.yaml")):
            raw = _read_yaml(file_path)
            scope_id = raw.get("group_id") or file_path.stem
            repo.create_rule_version(
                scope_type="group",
                scope_id=scope_id,
                source="manual",
                document=_normalise_style_document(raw),
            )


def recover_stale_runs(context: ContextManager) -> int:
    from src.control.repositories.analysis_repository import AnalysisRepository
    repo = AnalysisRepository(context)
    return repo.recover_stale()


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _normalise_style_document(raw: dict[str, Any]) -> dict[str, Any]:
    metadata = {
        key: value
        for key, value in raw.items()
        if key != "chat_rules"
    }
    return {
        "metadata": metadata,
        "chat_rules": raw.get("chat_rules", {}),
    }
