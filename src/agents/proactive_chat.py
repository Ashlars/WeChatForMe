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

            # Always resolve latest name from groups/contacts table (not stale proactive_chats.chat_name)
            chat_name = row["chat_name"]
            if row["chat_type"] == "group":
                group = self._context.get_group(chat_id)
                if group and group.group_name:
                    chat_name = group.group_name
            else:
                contact = self._context.get_contact(chat_id)
                if contact:
                    chat_name = contact.remark or contact.nickname or chat_name

            logger.info("Proactive chat: {} -> {} (topic: {})", chat_id, chat_name, topic)
            self._send_proactive(chat_id, row["chat_type"], chat_name, topic)

            with self._context._lock:
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

        # Get user persona with per-chat context
        chat_persona_ctx = None
        if chat_type == "group":
            group_obj = self._context.get_group(chat_id)
            if group_obj and group_obj.persona_context:
                chat_persona_ctx = group_obj.persona_context
        else:
            contact_obj = self._context.get_contact(chat_id)
            if contact_obj and contact_obj.persona_context:
                chat_persona_ctx = contact_obj.persona_context
        user_persona = self._build_user_persona(chat_persona_ctx)

        # Topic keywords for context
        topic_kws = [kw.strip() for kw in topic.replace("，", ",").split(",") if kw.strip()]
        topic_desc = "、".join(topic_kws)

        # Build member info for groups
        members_info = ""
        if chat_type == "group":
            members_info = self._build_group_members_info(chat_id)

        # Get user aliases
        user_aliases = self._context.get_config("user_aliases", "")
        alias_warning = ""
        if user_aliases:
            alias_warning = f"\n注意：「{user_aliases}」这些是别人叫你的称呼，绝对不要用这些去叫别人！"

        # Get recent proactive messages to avoid repetition
        recent_proactive = self._context._conn.execute(
            """SELECT content FROM messages
               WHERE msg_id LIKE 'proactive_%' AND (group_id = ? OR contact_id = ?)
               ORDER BY created_at DESC LIMIT 5""",
            (chat_id, chat_id),
        ).fetchall()
        dedup_text = ""
        if recent_proactive:
            dedup_lines = [r["content"][:60] for r in recent_proactive]
            dedup_text = "\n你最近已经发过这些消息，绝对不要重复类似的内容:\n" + "\n".join(f"  × {l}" for l in dedup_lines) + "\n"

        # If no trending at all, tell LLM explicitly
        no_trending_hint = ""
        if not trending:
            no_trending_hint = f"\n（没有抓到实时热点，请根据你对「{topic_desc}」的了解，聊一个具体的、有时效感的话题）"

        prompt = f"""现在是 {now_str}，你正在刷手机，想在微信里跟朋友聊点跟「{topic_desc}」有关的。

{f'你刚看到的实时资讯（必须基于这些内容来聊）:{chr(10)}{trending}{chr(10)}' if trending else ''}{no_trending_hint}{dedup_text}{f'之前的聊天:{chr(10)}{history_text}{chr(10)}' if history_text else ''}{members_info}
要求:
- 必须聊一个具体的事情（某场比赛、某个新闻、某个事件），不要空泛
- 如果上面有实时资讯，必须从中选一个来聊，用自己的话说出来
- 不要重复你之前发过的类似内容
- 像给朋友发消息一样自然
- 如果要提到群里的人，用设置的称呼{alias_warning}
- 只输出消息内容，1-2句话

{f'{user_persona}' if user_persona else ''}{f'聊天风格:{chr(10)}{style}' if style else ''}"""

        try:
            message = client.create_message(
                model=model,
                max_tokens=2000,
                system=f"你就是这个微信用户本人，正在「{chat_name or chat_id}」里发消息。只针对这一个聊天，不要混入其他聊天的内容。只输出消息内容，不要引号、不要前缀、不要解释。",
                messages=[{"role": "user", "content": prompt}],
            )

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
            else:
                logger.error("Proactive message FAILED to send to {}: {}", target, message[:50])

        except Exception:
            logger.exception("Failed to generate/send proactive message to {}", chat_id)

    def _fetch_trending(self, topic: str) -> str:
        """Fetch real-time trending topics. Always returns something."""
        topic_kws = [kw.strip() for kw in topic.replace("，", ",").split(",") if kw.strip()]

        # Try fetching hot lists
        relevant = []
        general = []
        for fetcher in [self._fetch_toutiao_hot, self._fetch_weibo_hot]:
            try:
                r, g = fetcher(topic)
                if r:
                    relevant.extend(r)
                if g:
                    general.extend(g)
                if relevant or general:
                    break
            except Exception:
                continue

        lines = []
        if relevant:
            lines.append("今日相关热点:\n" + "\n".join(f"  - {t}" for t in relevant[:5]))
        if general:
            lines.append("今日热点（可作为话题灵感）:\n" + "\n".join(f"  - {t}" for t in general[:5]))
        return "\n".join(lines)

    def _fetch_toutiao_hot(self, topic: str) -> tuple[list[str], list[str]]:
        """Fetch Toutiao hot topics. Returns (relevant, general)."""
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
        general = titles[:8]
        return relevant, general

    def _fetch_weibo_hot(self, topic: str) -> tuple[list[str], list[str]]:
        """Fetch Weibo hot search. Returns (relevant, general)."""
        resp = httpx.get(
            "https://weibo.com/ajax/side/hotSearch",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=5,
        )
        data = resp.json().get("data", {}).get("realtime", [])
        if not data:
            return [], []

        words = [item.get("word", "") for item in data if item.get("word")]
        topic_kws = [kw.strip() for kw in topic.replace("，", ",").split(",") if kw.strip()]
        relevant = [w for w in words if any(kw.lower() in w.lower() for kw in topic_kws)][:5]
        general = words[:8]
        return relevant, general

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

    def _build_group_members_info(self, group_id: str) -> str:
        """Build info about group members so AI knows who's in the group and what to call them."""
        rows = self._context._conn.execute(
            """SELECT gm.nickname, gm.my_alias_for AS gm_alias,
                      c.my_alias_for AS c_alias, c.remark AS c_remark
               FROM group_members gm
               LEFT JOIN contacts c ON gm.wxid = c.wxid
               WHERE gm.group_id = ?
               ORDER BY gm.msg_count DESC LIMIT 15""",
            (group_id,),
        ).fetchall()
        if not rows:
            return ""

        lines = ["群里的人:"]
        for r in rows:
            nickname = r["nickname"] or "未知"
            my_alias = r["gm_alias"] or r["c_alias"] or ""
            remark = r["c_remark"] or ""
            display = remark or nickname
            if my_alias:
                lines.append(f"  - {display}（我叫TA: {my_alias}）")
            else:
                lines.append(f"  - {display}")
        lines.append("")
        return "\n".join(lines) + "\n"

    def _build_user_persona(self, chat_persona_ctx: str | None = None) -> str:
        from src.core.llm import build_user_persona
        return build_user_persona(self._context, persona_context=chat_persona_ctx)

    def _get_client_and_model(self) -> tuple[anthropic.Anthropic, str]:
        from src.core.llm import get_client_and_model
        return get_client_and_model(self._context, prefix="chat")
