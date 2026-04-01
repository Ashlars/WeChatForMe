from __future__ import annotations

import os
import threading
import time
import uuid
from datetime import datetime

import anthropic
import httpx
from loguru import logger

from src.backend.base import WeChatBackend
from src.core.context import ContextManager
from src.core.style import StyleManager
from src.models.schemas import Message, MessageDirection


class ProactiveChatManager:
    """Periodically sends topic-based messages in configured chats."""

    def __init__(
        self,
        backend: WeChatBackend,
        context: ContextManager,
        style_manager: StyleManager,
    ) -> None:
        self._backend = backend
        self._context = context
        self._style_manager = style_manager
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("ProactiveChatManager started")

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        while self._running:
            time.sleep(30)
            try:
                self._check_and_send()
            except Exception:
                logger.exception("Proactive chat loop error")

    def _check_and_send(self) -> None:
        rows = self._context._conn.execute(
            "SELECT * FROM proactive_chats WHERE enabled = 1"
        ).fetchall()

        now = datetime.now()
        for row in rows:
            chat_id = row["id"]
            interval = row["interval_minutes"]
            topic = row["topic"]
            last_sent = row["last_sent_at"]

            if last_sent:
                last_dt = datetime.fromisoformat(last_sent)
                elapsed = (now - last_dt).total_seconds() / 60
                if elapsed < interval:
                    continue

            logger.info("Proactive chat: {} (topic: {})", chat_id, topic)
            self._send_proactive(chat_id, row["chat_type"], row["chat_name"], topic)

            self._context._conn.execute(
                "UPDATE proactive_chats SET last_sent_at = ? WHERE id = ?",
                (now.isoformat(), chat_id),
            )
            self._context._conn.commit()

    def _send_proactive(self, chat_id: str, chat_type: str, chat_name: str | None, topic: str) -> None:
        client, model = self._get_client_and_model()

        # Get recent history
        if chat_type == "group":
            history = self._context.get_recent_messages("", group_id=chat_id, limit=20)
        else:
            history = self._context.get_recent_messages(chat_id, limit=20)

        history_text = "\n".join(
            f"[{'我' if m.direction == MessageDirection.OUTGOING else '对方'}] {m.content}"
            for m in history[-10:]
        )

        # Get style config
        if chat_type == "group":
            style = self._style_manager.format_style_prompt(group_id=chat_id)
        else:
            style = self._style_manager.format_style_prompt(contact_id=chat_id)

        # Fetch real-time trending topics
        trending = self._fetch_trending(topic)

        now_str = datetime.now().strftime("%Y年%m月%d日 %H:%M")

        # Get user persona for natural style
        user_persona = self._build_user_persona()

        # Topic keywords for context
        topic_kws = [kw.strip() for kw in topic.replace("，", ",").split(",") if kw.strip()]
        topic_desc = "、".join(topic_kws)

        prompt = f"""现在是 {now_str}，你正在刷手机，看到了一些跟「{topic_desc}」相关的内容，想在微信群/私聊里跟朋友分享或聊聊。

{f'你刚看到的相关资讯:{chr(10)}{trending}{chr(10)}' if trending else ''}
{f'之前的聊天:{chr(10)}{history_text}{chr(10)}' if history_text else ''}
想象一下你是怎么跟朋友聊天的——
你不会说"我来聊聊足球"这种话，你会直接说"卧槽昨晚那球看了没"或者"刚刷到xx，绝了"。

要求:
- 必须围绕「{topic_desc}」相关的具体事情说，不要偏离主题
- 如果有实时资讯，挑一个最值得聊的，用自己的话说出来
- 如果没有实时资讯，可以聊「{topic_desc}」相关的经历、观点、疑问
- 像给朋友发消息一样，不要像在写文章
- 可以带点个人看法或吐槽
- 只输出消息内容，1-2句话

{f'{user_persona}' if user_persona else ''}{f'聊天风格:{chr(10)}{style}' if style else ''}"""

        try:
            response = client.messages.create(
                model=model,
                max_tokens=200,
                system=f"你就是这个微信用户本人。用TA的说话方式发一条消息。只输出消息内容，不要引号、不要前缀、不要解释。",
                messages=[{"role": "user", "content": prompt}],
            )
            message = response.content[0].text.strip()

            if not message:
                return

            # Optionally prepend AI label
            send_text = message
            if self._context.get_config("ai_label_enabled", "0") == "1":
                label = self._context.get_config("ai_label_text", "[AI]")
                send_text = f"{label} {message}"

            target = chat_name or chat_id
            success = self._backend.send_message(target, send_text)

            if success:
                _, used_model = self._get_client_and_model()
                self._context.save_message(Message(
                    msg_id=f"proactive_{uuid.uuid4().hex[:12]}",
                    contact_id=chat_id if chat_type == "private" else "",
                    group_id=chat_id if chat_type == "group" else None,
                    direction=MessageDirection.OUTGOING,
                    content=message,
                    agent_model=used_model,
                ))
                logger.info("Proactive message sent to {}: {}", target, message[:50])

        except Exception:
            logger.exception("Failed to send proactive message to {}", chat_id)

    def _fetch_trending(self, topic: str) -> str:
        """Fetch real-time trending topics related to the given theme."""
        topic_kws = [kw.strip() for kw in topic.replace("，", ",").split(",") if kw.strip()]

        results = []
        for fetcher in [self._fetch_toutiao_hot, self._fetch_weibo_hot]:
            try:
                result = fetcher(topic)
                if result:
                    results.append(result)
                    break
            except Exception:
                continue

        # If no topic-specific results from hot lists, try a direct search
        if not results:
            try:
                search_result = self._search_topic(topic_kws)
                if search_result:
                    results.append(search_result)
            except Exception:
                pass

        return "\n".join(results)

    def _fetch_toutiao_hot(self, topic: str) -> str:
        """Fetch Toutiao hot topics, prioritize topic-relevant ones."""
        try:
            resp = httpx.get(
                "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc",
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=5,
            )
            data = resp.json().get("data", [])
            titles = [item.get("Title", "") for item in data if item.get("Title")]

            topic_kws = [kw.strip() for kw in topic.replace("，", ",").split(",") if kw.strip()]
            relevant = [
                t for t in titles
                if any(kw.lower() in t.lower() for kw in topic_kws)
            ][:5]

            # Only return if we found relevant items — don't pollute with unrelated hot topics
            if relevant:
                return "今日相关热点:\n" + "\n".join(f"  - {t}" for t in relevant)
            return ""
        except Exception:
            return ""

    def _fetch_weibo_hot(self, topic: str) -> str:
        """Fetch Weibo hot search, only return topic-relevant items."""
        try:
            resp = httpx.get(
                "https://weibo.com/ajax/side/hotSearch",
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=5,
            )
            data = resp.json().get("data", {}).get("realtime", [])
            if not data:
                return ""

            topic_kws = [kw.strip() for kw in topic.replace("，", ",").split(",") if kw.strip()]
            relevant = [
                item["word"] for item in data
                if any(kw.lower() in item.get("word", "").lower() for kw in topic_kws)
            ][:5]

            if relevant:
                return "微博相关热搜:\n" + "\n".join(f"  - {t}" for t in relevant)
            return ""
        except Exception:
            return ""

    def _search_topic(self, keywords: list[str]) -> str:
        """Search for recent news about specific topic keywords."""
        query = " ".join(keywords)
        try:
            resp = httpx.get(
                "https://www.toutiao.com/api/search/content/",
                params={"keyword": query, "count": 5, "offset": 0},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=5,
            )
            data = resp.json().get("data", [])
            if not data:
                return ""
            titles = [item.get("title", "") for item in data if item.get("title")][:5]
            if titles:
                return "搜索到的相关资讯:\n" + "\n".join(f"  - {t}" for t in titles)
        except Exception:
            pass
        return ""

    def _build_user_persona(self) -> str:
        fields = [
            ("user_personality", "性格"),
            ("user_speaking_style", "说话风格"),
            ("user_habits", "口头禅和习惯"),
            ("user_tone", "语气"),
        ]
        lines = []
        for key, label in fields:
            val = self._context.get_config(key, "")
            if val:
                lines.append(f"- {label}: {val}")
        if not lines:
            return ""
        return "你的人设:\n" + "\n".join(lines) + "\n"

    def _get_client_and_model(self) -> tuple[anthropic.Anthropic, str]:
        api_key = (
            self._context.get_config("chat_api_key", "")
            or os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
            or os.environ.get("ANTHROPIC_API_KEY", "")
        )
        base_url = (
            self._context.get_config("chat_api_base_url", "")
            or os.environ.get("ANTHROPIC_BASE_URL", None)
        )
        model = (
            self._context.get_config("chat_api_model", "")
            or os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL", "")
            or "claude-sonnet-4-6"
        )
        client = anthropic.Anthropic(
            api_key=api_key,
            base_url=base_url or None,
        )
        return client, model
