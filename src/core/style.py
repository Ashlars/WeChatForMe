from __future__ import annotations

from pathlib import Path

import yaml
from loguru import logger


class StyleManager:
    def __init__(self, style_dir: Path) -> None:
        self._style_dir = Path(style_dir)
        self._default_rules: dict = {}
        self._contact_configs: dict[str, dict] = {}  # keyed by wxid
        self._group_configs: dict[str, dict] = {}    # keyed by group_id
        # Also keep name→config lookup for convenience
        self._contact_by_name: dict[str, dict] = {}
        self._group_by_name: dict[str, dict] = {}
        self.reload()

    def reload(self) -> None:
        # Load default
        default_path = self._style_dir / "default.yaml"
        if default_path.exists():
            with open(default_path) as f:
                data = yaml.safe_load(f) or {}
                self._default_rules = data.get("chat_rules", {})

        # Load per-contact configs
        self._contact_configs = {}
        self._contact_by_name = {}
        contacts_dir = self._style_dir / "contacts"
        if contacts_dir.exists():
            for f in contacts_dir.glob("*.yaml"):
                with open(f) as fh:
                    data = yaml.safe_load(fh) or {}
                wxid = data.get("wxid", f.stem)
                self._contact_configs[wxid] = data
                self._contact_by_name[f.stem] = data

        # Load per-group configs
        self._group_configs = {}
        self._group_by_name = {}
        groups_dir = self._style_dir / "groups"
        if groups_dir.exists():
            for f in groups_dir.glob("*.yaml"):
                with open(f) as fh:
                    data = yaml.safe_load(fh) or {}
                group_id = data.get("group_id", f.stem)
                self._group_configs[group_id] = data
                self._group_by_name[f.stem] = data

        logger.debug(
            "Loaded styles: {} contacts, {} groups",
            len(self._contact_configs),
            len(self._group_configs),
        )

    # ── public API ───────────────────────────────────────────────

    def get_chat_rules(
        self,
        *,
        contact_id: str | None = None,
        group_id: str | None = None,
    ) -> dict:
        """Return merged chat_rules: default ← per-contact/group override."""
        rules = dict(self._default_rules)

        if group_id and group_id in self._group_configs:
            group_rules = self._group_configs[group_id].get("chat_rules", {})
            rules = _deep_merge(rules, group_rules)
        elif contact_id and contact_id in self._contact_configs:
            contact_rules = self._contact_configs[contact_id].get("chat_rules", {})
            rules = _deep_merge(rules, contact_rules)

        return rules

    def get_forbidden_patterns(
        self,
        *,
        contact_id: str | None = None,
        group_id: str | None = None,
    ) -> list[str]:
        rules = self.get_chat_rules(contact_id=contact_id, group_id=group_id)
        return rules.get("forbidden_patterns", [])

    def get_full_config(
        self,
        *,
        contact_id: str | None = None,
        group_id: str | None = None,
    ) -> dict:
        """Return the full raw config (not just chat_rules) for a contact/group."""
        if group_id and group_id in self._group_configs:
            return self._group_configs[group_id]
        if contact_id and contact_id in self._contact_configs:
            return self._contact_configs[contact_id]
        return {}

    def format_style_prompt(
        self,
        *,
        contact_id: str | None = None,
        group_id: str | None = None,
    ) -> str:
        """Format chat config into a readable prompt for the LLM."""
        full_config = self.get_full_config(contact_id=contact_id, group_id=group_id)
        rules = self.get_chat_rules(contact_id=contact_id, group_id=group_id)
        if not rules and not full_config:
            return ""

        parts: list[str] = []

        # Description / intro (group or contact)
        if full_config.get("description"):
            parts.append(f"【背景】{full_config['description']}")
            parts.append("")

        # Contact-specific fields
        if full_config.get("relationship"):
            parts.append(f"- 你们的关系: {full_config['relationship']}")
        if full_config.get("their_role"):
            parts.append(f"- 对方的身份: {full_config['their_role']}")

        # Member roles (for groups)
        members = full_config.get("members", {})
        if members:
            parts.append("【群成员信息】")
            for name, info in members.items():
                role = info.get("role", "")
                notes = info.get("notes", "")
                line = f"- {name}: {role}"
                if notes:
                    line += f" ({notes})"
                parts.append(line)
            parts.append("")

        # Chat rules
        label_map = {
            "role": "你的身份",
            "personality": "性格特点",
            "tone": "语气",
            "reply_length": "回复长度",
            "emoji_usage": "表情使用",
        }

        rule_lines = []
        for key, label in label_map.items():
            if key in rules:
                rule_lines.append(f"- {label}: {rules[key]}")

        if rules.get("topics"):
            rule_lines.append(f"- 常聊话题: {', '.join(rules['topics'])}")

        if rules.get("avoid"):
            rule_lines.append(f"- 不要聊: {', '.join(rules['avoid'])}")

        if rule_lines:
            parts.append("【聊天规则】")
            parts.extend(rule_lines)
            parts.append("")

        if rules.get("special_instructions"):
            parts.append("【特殊要求（必须遵守）】")
            for inst in rules["special_instructions"]:
                parts.append(f"· {inst}")
            parts.append("")

        if rules.get("forbidden_patterns"):
            parts.append(f"【绝对禁止使用的表达】: {', '.join(rules['forbidden_patterns'])}")

        return "\n".join(parts)

    # Keep backward compat for old code that calls get_style()
    def get_style(self, contact_id: str | None = None) -> dict:
        return self.get_chat_rules(contact_id=contact_id)


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base. Lists are replaced, not appended."""
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
