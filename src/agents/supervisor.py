from __future__ import annotations

import json
import re

import os

import anthropic
from loguru import logger

from src.core.config import ConfigManager
from src.core.context import ContextManager
from src.core.style import StyleManager
from src.models.schemas import Message, MessageDirection


LEVEL_2_KEYS = {"whitelist_add", "whitelist_remove", "cron_change", "major_style_change"}


class SupervisorAgent:
    def __init__(
        self,
        context: ContextManager,
        config: ConfigManager,
        style_manager: StyleManager,
    ) -> None:
        self._context = context
        self._config = config
        self._style_manager = style_manager
        self._model = config.get("claude.supervisor_model", "claude-opus-4-6")
        self._client = anthropic.Anthropic(
            api_key=os.environ.get("ANTHROPIC_AUTH_TOKEN", os.environ.get("ANTHROPIC_API_KEY", "")),
            base_url=os.environ.get("ANTHROPIC_BASE_URL", None),
        )

    def run_analysis(self) -> None:
        logger.info("Supervisor: starting periodic analysis")
        contacts = self._context.get_whitelist_contacts()
        for contact in contacts:
            messages = self._context.get_recent_messages(contact.wxid, limit=50)
            if not messages:
                continue
            self._analyze_contact(contact.wxid, messages)

    def check_anomaly(self, contact_id: str, latest_message: str) -> bool:
        if self._detect_anomaly(latest_message):
            logger.warning("Anomaly detected from {}: {}", contact_id, latest_message)
            return True
        return False

    def _analyze_contact(self, contact_id: str, messages: list[Message]) -> None:
        try:
            prompt = self._build_analysis_prompt(messages)
            response = self._client.messages.create(
                model=self._model,
                max_tokens=1000,
                system="你是一个聊天质量分析专家。分析以下聊天记录，评估AI回复的质量。",
                messages=[{"role": "user", "content": prompt}],
            )
            analysis = response.content[0].text
            logger.info("Supervisor analysis for {}: {}", contact_id, analysis[:100])
        except Exception as e:
            logger.error("Supervisor analysis failed: {}", e)

    def _build_analysis_prompt(self, messages: list[Message]) -> str:
        current_style = self._style_manager.get_style()
        chat_log = []
        for m in messages:
            prefix = "[AI回复]" if m.direction == MessageDirection.OUTGOING else "[对方]"
            chat_log.append(f"{prefix} {m.content}")

        return f"""当前聊天风格设置: {json.dumps(current_style, ensure_ascii=False)}

最近聊天记录:
{chr(10).join(chat_log)}

请分析:
1. AI回复是否自然、符合风格设置?
2. 对方的反应如何（积极/消极/困惑）?
3. 建议哪些风格调整?

以JSON格式返回建议的调整。"""

    def _detect_anomaly(self, text: str) -> bool:
        negative_patterns = [
            r"[？?]{3,}",
            r"什么(鬼|意思|东西)",
            r"(滚|傻|蠢|笨)",
            r"不要.*(回复|消息|发)",
            r"(机器人|AI|人工智能)",
        ]
        for pattern in negative_patterns:
            if re.search(pattern, text):
                return True
        return False

    def _classify_change_level(self, changes: dict) -> int:
        for key in changes:
            if key in LEVEL_2_KEYS:
                return 2
        return 1
