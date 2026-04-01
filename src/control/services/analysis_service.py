from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import anthropic
from loguru import logger

from src.control.repositories.analysis_repository import AnalysisRepository
from src.control.repositories.event_repository import EventRepository
from src.control.repositories.review_repository import ReviewRepository
from src.control.services.rule_service import RuleService
from src.core.context import ContextManager


class AnalysisService:
    def __init__(
        self,
        context: ContextManager,
        *,
        style_dir: str | Path,
        client: anthropic.Anthropic | None = None,
        model: str | None = None,
    ) -> None:
        self._context = context
        self._analysis_repo = AnalysisRepository(context)
        self._review_repo = ReviewRepository(context)
        self._event_repo = EventRepository(context)
        self._rule_service = RuleService(context, style_dir)
        self._override_model = model
        self._override_client = client

    def _get_client_and_model(self) -> tuple[anthropic.Anthropic, str]:
        if self._override_client:
            model = self._override_model or "claude-sonnet-4-6"
            return self._override_client, model

        api_key = (
            self._context.get_config("analysis_api_key", "")
            or os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
            or os.environ.get("ANTHROPIC_API_KEY", "")
        )
        base_url = (
            self._context.get_config("analysis_api_base_url", "")
            or os.environ.get("ANTHROPIC_BASE_URL", None)
        )
        model = (
            self._context.get_config("analysis_api_model", "")
            or self._override_model
            or os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL", "")
            or "claude-sonnet-4-6"
        )
        client = anthropic.Anthropic(
            api_key=api_key,
            base_url=base_url or None,
        )
        return client, model

    def run_analysis(
        self, *, target_type: str, target_id: str, trigger_type: str,
    ) -> dict[str, Any]:
        run = self._analysis_repo.create_run(
            target_type=target_type, target_id=target_id, trigger_type=trigger_type,
        )
        run_id = run["id"]
        self._analysis_repo.mark_running(run_id)

        try:
            context_data = self._build_context(target_type, target_id)
            prompt = self._build_prompt(target_type, target_id, context_data)

            client, model = self._get_client_and_model()
            response = client.messages.create(
                model=model,
                max_tokens=4000,
                system="你是一个聊天分析专家。分析聊天记录，提取对方的人物画像、聊天风格，并给出规则建议。必须返回严格的JSON格式。",
                messages=[{"role": "user", "content": prompt}],
            )
            raw_output = response.content[0].text
            parsed = self._parse_output(raw_output)

            persona_json = json.dumps(parsed, ensure_ascii=False)
            suggestions = parsed.get("recommended_rule_changes", [])
            suggestions_json = json.dumps(suggestions, ensure_ascii=False)

            self._analysis_repo.mark_succeeded(
                run_id,
                summary=parsed.get("persona_summary", ""),
                persona_json=persona_json,
                suggestions_json=suggestions_json,
            )

            self._apply_profile_to_db(target_type, target_id, parsed)
            self._generate_review_items(run_id, target_type, target_id, parsed)

            self._event_repo.log("analysis_succeeded", "info",
                                 f"Analysis completed for {target_type}/{target_id}")

            return self._analysis_repo.get_run(run_id)

        except Exception as e:
            error_msg = str(e)
            logger.error("Analysis failed for {}/{}: {}", target_type, target_id, error_msg)
            self._analysis_repo.mark_failed(run_id, error_message=error_msg)
            self._event_repo.log("analysis_failed", "error",
                                 f"Analysis failed for {target_type}/{target_id}: {error_msg}")
            return self._analysis_repo.get_run(run_id)

    def _build_context(self, target_type: str, target_id: str) -> dict[str, Any]:
        if target_type == "contact":
            contact = self._context.get_contact(target_id)
            # Use human-only messages for analysis (exclude AI-generated replies)
            messages = self._context.get_recent_messages_human_only(target_id, limit=80)
            rule = self._rule_service.get_rule("contact", target_id)
            return {
                "contact": contact.model_dump(mode="json") if contact else {},
                "messages": [m.model_dump(mode="json") for m in messages],
                "current_rule": rule.get("document", {}) if rule else {},
            }
        else:
            group = self._context.get_group(target_id)
            # Use human-only messages for analysis
            messages = self._context.get_recent_messages_human_only("", group_id=target_id, limit=120)
            rule = self._rule_service.get_rule("group", target_id)
            return {
                "group": group.model_dump(mode="json") if group else {},
                "messages": [m.model_dump(mode="json") for m in messages],
                "current_rule": rule.get("document", {}) if rule else {},
            }

    def _build_prompt(self, target_type: str, target_id: str, context: dict) -> str:
        messages_text = "\n".join(
            f"[{'AI' if m['direction'] == 'outgoing' else '对方'}] {m['content']}"
            for m in context["messages"]
        )

        if target_type == "contact":
            contact_info = context.get("contact", {})
            return f"""分析以下微信私聊记录，提取对方的人物画像和聊天风格。

联系人信息:
- 昵称: {contact_info.get('nickname', '未知')}
- 关系: {contact_info.get('relationship', '未知')}

当前聊天规则:
{json.dumps(context.get('current_rule', {}), ensure_ascii=False, indent=2)}

最近聊天记录:
{messages_text}

请返回以下JSON格式的分析结果:
{{
  "persona_summary": "对方人物画像摘要",
  "native_style_summary": "对方本人聊天风格摘要",
  "preferred_interaction_style": "对方更适应的互动方式",
  "relationship_notes": ["关系观察"],
  "recommended_rule_changes": [
    {{"scope_type": "contact", "path": "chat_rules.字段名", "operation": "set", "value": "新值", "reason": "原因"}}
  ],
  "recommended_profile_changes": [
    {{"target_type": "contact", "field": "字段名", "value": "新值", "reason": "原因"}}
  ],
  "recommended_state_changes": [],
  "confidence": 0.0到1.0,
  "evidence": [{{"message_ids": [], "summary": "", "observation": ""}}]
}}"""
        else:
            group_info = context.get("group", {})
            return f"""分析以下微信群聊记录，提取群聊氛围和回复策略建议。

群聊信息:
- 群名: {group_info.get('group_name', '未知')}

当前聊天规则:
{json.dumps(context.get('current_rule', {}), ensure_ascii=False, indent=2)}

最近群聊记录:
{messages_text}

请返回以下JSON格式的分析结果:
{{
  "persona_summary": "群聊氛围摘要",
  "native_style_summary": "群聊主要风格",
  "preferred_interaction_style": "建议的参与方式",
  "relationship_notes": ["群聊观察"],
  "recommended_rule_changes": [
    {{"scope_type": "group", "path": "chat_rules.字段名", "operation": "set", "value": "新值", "reason": "原因"}}
  ],
  "recommended_profile_changes": [
    {{"target_type": "group", "field": "字段名", "value": "新值", "reason": "原因"}}
  ],
  "recommended_state_changes": [],
  "confidence": 0.0到1.0,
  "evidence": [{{"message_ids": [], "summary": "", "observation": ""}}]
}}"""

    def _parse_output(self, raw: str) -> dict[str, Any]:
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
        return json.loads(text.strip())

    def _apply_profile_to_db(self, target_type: str, target_id: str, parsed: dict) -> None:
        now_iso = datetime.now().isoformat()
        if target_type == "contact":
            self._context._conn.execute(
                """UPDATE contacts SET persona_summary = ?, style_summary = ?,
                   interaction_style_summary = ?, last_analysis_at = ?
                   WHERE wxid = ?""",
                (
                    parsed.get("persona_summary"),
                    parsed.get("native_style_summary"),
                    parsed.get("preferred_interaction_style"),
                    now_iso,
                    target_id,
                ),
            )
        else:
            self._context._conn.execute(
                """UPDATE groups SET group_profile = ?, reply_strategy = ?, last_analysis_at = ?
                   WHERE group_id = ?""",
                (
                    parsed.get("persona_summary"),
                    parsed.get("preferred_interaction_style"),
                    now_iso,
                    target_id,
                ),
            )
        self._context._conn.commit()

    def _generate_review_items(
        self, run_id: int, target_type: str, target_id: str, parsed: dict,
    ) -> None:
        for change in parsed.get("recommended_rule_changes", []):
            self._review_repo.create_item(
                review_type="rule_change",
                target_type=target_type,
                target_id=target_id,
                analysis_run_id=run_id,
                proposed_payload=change,
                rationale={"reason": change.get("reason", "")},
            )

        for change in parsed.get("recommended_profile_changes", []):
            rt = "contact_profile_change" if change.get("target_type") == "contact" else "group_profile_change"
            self._review_repo.create_item(
                review_type=rt,
                target_type=target_type,
                target_id=target_id,
                analysis_run_id=run_id,
                proposed_payload=change,
                rationale={"reason": change.get("reason", "")},
            )

        for change in parsed.get("recommended_state_changes", []):
            self._review_repo.create_item(
                review_type="contact_state_change",
                target_type="contact",
                target_id=target_id,
                analysis_run_id=run_id,
                proposed_payload=change,
                rationale={"reason": change.get("reason", "")},
            )
