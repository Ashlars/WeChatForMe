from __future__ import annotations

import json
import threading
import time
import uuid
from collections import defaultdict

import os

import anthropic
from loguru import logger

from src.backend.base import IncomingMessage, WeChatBackend
from src.core.config import ConfigManager
from src.core.context import ContextManager
from src.core.security import SecurityManager
from src.core.style import StyleManager
from src.models.schemas import Contact, Message, MessageDirection


class ChatAgent:
    def __init__(
        self,
        backend: WeChatBackend,
        context: ContextManager,
        config: ConfigManager,
        security: SecurityManager,
        style_manager: StyleManager,
    ) -> None:
        self._backend = backend
        self._context = context
        self._config = config
        self._security = security
        self._style_manager = style_manager

        self._user_name = config.get("user.name", "我")
        self._chat_model = config.get("claude.chat_model", "claude-sonnet-4-6")

        # Private chat config
        self._max_reply_length = config.get("reply_rules.private_chat.max_reply_length", 200)
        self._whitelist_only = config.get("reply_rules.private_chat.whitelist_only", True)
        self._private_delay_range = config.get("reply_rules.private_chat.delay_range", [2, 8])
        self._private_history_limit = config.get("reply_rules.private_chat.history_limit", 20)

        # Group chat config
        self._group_delay_range = config.get("reply_rules.group_chat.delay_range", [3, 15])
        self._group_history_limit = config.get("reply_rules.group_chat.history_limit", 30)
        self._group_collect_window = config.get("reply_rules.group_chat.collect_window", 10)
        self._group_max_reply_length = config.get("reply_rules.group_chat.max_reply_length", 200)

        self._forbidden_patterns = style_manager.get_chat_rules().get("forbidden_patterns", [])

        # Group message batching state
        self._collect_timers: dict[str, threading.Timer] = {}
        self._collect_lock = threading.Lock()

        backend.on_new_message(self.handle_message)

    # ── message entry point ──────────────────────────────────────

    def handle_message(self, msg: IncomingMessage) -> None:
        try:
            self._handle_message_inner(msg)
        except Exception:
            logger.exception("Error handling message from {}", msg.sender_name)

    def _handle_message_inner(self, msg: IncomingMessage) -> None:
        # Always save message to DB
        self._context.save_message(Message(
            msg_id=msg.msg_id or f"in_{uuid.uuid4().hex[:12]}",
            contact_id=msg.sender_id,
            group_id=msg.group_id,
            direction=MessageDirection.INCOMING,
            content=msg.content,
        ))

        # Auto-create contact/group records if not exists
        self._ensure_records(msg)

        # --- Auto-reply logic below ---

        # Global auto-reply toggle
        if self._context.get_config("auto_reply_enabled", "1") != "1":
            return

        if not self._should_respond(msg):
            logger.debug("Skipping message from {} (should_respond=False)", msg.sender_name)
            return

        if self._security.is_pause_command(msg.content):
            self._handle_pause(msg)
            return

        if self._security.contains_sensitive(msg.content):
            logger.info("Skipping message with sensitive content from {}", msg.sender_name)
            return

        if not self._security.check_rate_limit(msg.sender_id):
            logger.info("Rate limit exceeded for {}", msg.sender_name)
            return

        if msg.is_group:
            self._enqueue_group_reply(msg)
        else:
            self._do_reply(msg)

    # ── group message batching ───────────────────────────────────

    def _enqueue_group_reply(self, msg: IncomingMessage) -> None:
        """Buffer group messages; reply after collect_window seconds of quiet."""
        chat_key = msg.group_id or msg.sender_id

        with self._collect_lock:
            # Cancel existing timer for this chat
            if chat_key in self._collect_timers:
                self._collect_timers[chat_key].cancel()

            logger.info(
                "Buffering group msg from {} in {} (waiting {}s for more)",
                msg.sender_name, msg.group_name, self._group_collect_window,
            )

            timer = threading.Timer(
                self._group_collect_window,
                self._flush_group_reply,
                args=[chat_key, msg],
            )
            timer.daemon = True
            timer.start()
            self._collect_timers[chat_key] = timer

    def _flush_group_reply(self, chat_key: str, last_msg: IncomingMessage) -> None:
        """Timer fired — generate one reply considering all recent group messages."""
        with self._collect_lock:
            self._collect_timers.pop(chat_key, None)

        logger.info("Collect window elapsed for {}, generating reply", last_msg.group_name)
        self._do_reply(last_msg)

    # ── reply logic ──────────────────────────────────────────────

    def _do_reply(self, msg: IncomingMessage) -> None:
        reply = self._generate_reply(msg)
        if not reply:
            return

        delay_range = self._group_delay_range if msg.is_group else self._private_delay_range
        delay = self._security.generate_delay(*delay_range)
        logger.info("Waiting {:.1f}s before replying to {}", delay, msg.sender_name)
        time.sleep(delay)

        # Optionally prepend AI label
        send_text = reply
        if self._context.get_config("ai_label_enabled", "0") == "1":
            label = self._context.get_config("ai_label_text", "[AI]")
            send_text = f"{label} {reply}"

        target = msg.group_name if msg.is_group else msg.sender_name
        success = self._backend.send_message(target, send_text)

        if success:
            self._security.record_reply(msg.sender_id)
            self._context.save_message(Message(
                msg_id=f"out_{uuid.uuid4().hex[:12]}",
                contact_id="__self__" if msg.is_group else msg.sender_id,
                group_id=msg.group_id,
                direction=MessageDirection.OUTGOING,
                content=reply,
                agent_model=self._chat_model,
            ))

    # ── proactive chat ───────────────────────────────────────────

    def handle_proactive_chat(self, contact: str, topic_hint: str) -> None:
        logger.info("Proactive chat: {} (topic: {})", contact, topic_hint)

        history = self._context.get_recent_messages(contact, limit=self._private_history_limit)
        system_prompt = self._build_system_prompt(contact)
        prompt = f"你要主动找对方聊天。话题方向: {topic_hint}。根据之前的聊天记录，自然地发起对话。"

        messages = self._build_messages(history, prompt, is_group=False)

        try:
            client, model = self._get_client_and_model()
            response = client.messages.create(
                model=model,
                max_tokens=self._max_reply_length * 2,
                system=system_prompt,
                messages=messages,
            )
            reply = self._clean_response(response.content[0].text, contact_id=contact)
            if reply:
                self._backend.send_message(contact, reply)
                self._context.save_message(Message(
                    msg_id=f"proactive_{uuid.uuid4().hex[:12]}",
                    contact_id=contact,
                    direction=MessageDirection.OUTGOING,
                    content=reply,
                    agent_model=self._chat_model,
                ))
        except Exception as e:
            logger.error("Proactive chat failed for {}: {}", contact, e)

    # ── should respond ───────────────────────────────────────────

    def _should_respond(self, msg: IncomingMessage) -> bool:
        if msg.is_group:
            row = self._context._conn.execute(
                "SELECT is_active, trigger_mode, keywords FROM groups WHERE group_id = ?",
                (msg.group_id,),
            ).fetchone()
            if not row or not row["is_active"]:
                return False

            trigger_mode = row["trigger_mode"] or "at_me"
            raw_keywords = row["keywords"] or "[]"
            try:
                keywords = json.loads(raw_keywords)
            except json.JSONDecodeError:
                keywords = [k.strip() for k in raw_keywords.split(",") if k.strip()]

            return self._check_trigger(msg.content, trigger_mode, keywords)

        contact = self._context.get_contact(msg.sender_id)
        if not contact:
            return not self._whitelist_only
        if contact.is_paused:
            return False
        if self._whitelist_only and not contact.is_whitelist:
            return False
        return True

    def _get_all_names(self) -> list[str]:
        """Get all names/aliases the user goes by."""
        names = [self._user_name]
        nick = self._context.get_config("user_nickname", "")
        if nick and nick not in names:
            names.append(nick)
        aliases = self._context.get_config("user_aliases", "")
        if aliases:
            for a in aliases.replace("，", ",").split(","):
                a = a.strip()
                if a and a not in names:
                    names.append(a)
        return names

    def _check_trigger(self, content: str, trigger_mode: str, keywords: list[str]) -> bool:
        if trigger_mode == "all":
            return True

        all_names = self._get_all_names()
        at_match = any(f"@{name}" in content for name in all_names)
        kw_match = any(kw in content for kw in keywords) if keywords else False

        if trigger_mode == "at_me":
            return at_match
        elif trigger_mode == "keyword":
            return kw_match
        elif trigger_mode == "both":
            return at_match or kw_match
        return False

    # ── reply generation ─────────────────────────────────────────

    def _generate_reply(self, msg: IncomingMessage) -> str | None:
        try:
            history_limit = self._group_history_limit if msg.is_group else self._private_history_limit
            max_len = self._group_max_reply_length if msg.is_group else self._max_reply_length

            history = self._context.get_recent_messages(
                msg.sender_id, group_id=msg.group_id, limit=history_limit,
            )
            system_prompt = self._build_system_prompt(
                msg.sender_id, is_group=msg.is_group,
                group_id=msg.group_id, group_name=msg.group_name,
            )
            messages = self._build_messages(history, msg.content, is_group=msg.is_group)

            client, model = self._get_client_and_model()
            logger.info("Calling API ({}) with {} history messages", model, len(history))
            response = client.messages.create(
                model=model,
                max_tokens=max_len * 2,
                system=system_prompt,
                messages=messages,
            )
            reply = response.content[0].text
            logger.info("Claude replied: {}", reply[:100])
            return self._clean_response(
                reply, contact_id=msg.sender_id, group_id=msg.group_id,
            )
        except Exception:
            logger.exception("Failed to generate reply")
            return None

    def _build_user_persona(self) -> str:
        """Build user persona description from DB config."""
        aliases = self._context.get_config("user_aliases", "")

        fields = [
            ("user_personality", "性格"),
            ("user_speaking_style", "说话风格"),
            ("user_habits", "口头禅和习惯"),
            ("user_topics", "感兴趣的话题"),
            ("user_tone", "语气特征"),
            ("user_extra", "补充"),
        ]
        lines = []
        if aliases:
            lines.append(f"- 别人可能叫你: {aliases}（这些都是在叫你，要回应）")
        for key, label in fields:
            val = self._context.get_config(key, "")
            if val:
                lines.append(f"- {label}: {val}")
        if not lines:
            return ""
        return "【你的人设（必须严格模仿）】\n" + "\n".join(lines) + "\n"

    def _build_system_prompt(
        self,
        contact_id: str | None = None,
        *,
        is_group: bool = False,
        group_id: str | None = None,
        group_name: str | None = None,
    ) -> str:
        style_prompt = self._style_manager.format_style_prompt(
            contact_id=contact_id, group_id=group_id,
        )
        contact = self._context.get_contact(contact_id) if contact_id else None
        relationship = contact.relationship if contact else "朋友"
        user_persona = self._build_user_persona()
        user_nick = self._context.get_config("user_nickname", "") or self._user_name

        if is_group:
            members_prompt = self._build_members_prompt(group_id) if group_id else ""
            return f"""你是{user_nick}，正在微信群「{group_name or '群聊'}」里聊天。

{user_persona}【最重要】区分不同的人：
- 消息格式为「[昵称] 内容」，不同的昵称是不同的人
- [{user_nick}(你自己)] 开头的是你之前说过的话
- 你必须清楚是谁在跟你说话，不要把 A 说的话当成 B 说的
- 回复时要针对正确的人

核心要求：
1. 针对别人刚说的话来回应，不要自说自话
2. 像真人一样接话、附和、反驳、追问
3. 根据每个人的特点，用不同方式回应不同的人
4. 只输出回复内容，不要任何前缀或标记
5. 一次只回复一条消息，简短自然

{members_prompt}【严格遵守以下聊天规则】:
{style_prompt}"""
        else:
            return f"""你是{user_nick}，正在用微信和{relationship}聊天。

{user_persona}核心要求：
1. 针对对方刚说的话来回应，不要自说自话
2. 像真人聊天一样，接住对方的话，自然回复
3. 只输出回复内容，不要任何解释或前缀

【严格遵守以下聊天规则】:
{style_prompt}"""

    def _build_messages(
        self, history: list[Message], current_content: str, *, is_group: bool = False,
    ) -> list[dict]:
        messages: list[dict] = []

        if is_group:
            # Split history into older context and recent new messages to reply to
            # Find the last message we sent — everything after it is "new"
            last_our_idx = -1
            for i, msg in enumerate(history):
                if msg.direction == MessageDirection.OUTGOING:
                    last_our_idx = i

            if last_our_idx >= 0 and last_our_idx < len(history) - 1:
                context_msgs = history[:last_our_idx + 1]
                new_msgs = history[last_our_idx + 1:]
            else:
                # No outgoing message in history, or it's the last one
                # Use all but the latest few as context
                split = max(0, len(history) - 5)
                context_msgs = history[:split]
                new_msgs = history[split:]

            def format_msg(msg: Message) -> str:
                if msg.direction == MessageDirection.OUTGOING:
                    return f"[{self._user_name}(你自己)] {msg.content}"
                sender = self._resolve_sender(msg.contact_id)
                return f"[{sender}] {msg.content}"

            # Build context block
            context_lines = [format_msg(m) for m in context_msgs]

            if context_lines:
                messages.append({
                    "role": "user",
                    "content": "以下是之前的群聊记录（作为背景参考）。注意：方括号里是发言者的名字，不同的名字是不同的人：\n" + "\n".join(context_lines),
                })
                messages.append({
                    "role": "assistant",
                    "content": "好的，我了解上下文了，我会注意区分不同的人。",
                })

            # Build the "new messages to reply to" block
            new_lines = [format_msg(m) for m in new_msgs]

            if new_lines:
                # Identify unique senders in new messages
                new_senders = []
                for m in new_msgs:
                    if m.direction != MessageDirection.OUTGOING:
                        name = self._resolve_sender(m.contact_id)
                        if name not in new_senders:
                            new_senders.append(name)

                sender_hint = f"（发言者: {', '.join(new_senders)}）" if new_senders else ""
                messages.append({
                    "role": "user",
                    "content": f"以下是刚发的新消息{sender_hint}，注意区分每个人，针对性地回复:\n" + "\n".join(new_lines),
                })
            else:
                messages.append({
                    "role": "user",
                    "content": f"对方刚说了: {current_content}\n请针对这句话回复。",
                })
        else:
            # Private chat: standard alternating user/assistant
            for msg in history:
                role = "assistant" if msg.direction == MessageDirection.OUTGOING else "user"
                messages.append({"role": role, "content": msg.content})
            # Ensure last message is from the other person
            if not messages or messages[-1]["role"] != "user":
                messages.append({"role": "user", "content": current_content})

        return messages

    def _build_members_prompt(self, group_id: str) -> str:
        """Build a prompt section describing known group members, merging contact data."""
        rows = self._context._conn.execute(
            """SELECT gm.nickname, gm.role, gm.personality, gm.style_notes, gm.notes,
                      c.relationship, c.persona_summary, c.style_summary, c.interaction_style_summary
               FROM group_members gm
               LEFT JOIN contacts c ON gm.wxid = c.wxid
               WHERE gm.group_id = ?
               AND (gm.role != '' OR gm.personality != '' OR gm.style_notes != '' OR gm.notes != ''
                    OR c.relationship IS NOT NULL OR c.persona_summary IS NOT NULL
                    OR c.style_summary IS NOT NULL)""",
            (group_id,),
        ).fetchall()
        if not rows:
            return ""

        lines = ["【群成员画像（根据每个人的特点调整回复方式）】"]
        for r in rows:
            name = r["nickname"] or "未知"
            parts = []
            # My alias for this person
            my_alias = None
            try:
                my_alias = r["my_alias_for"]
            except (IndexError, KeyError):
                pass
            if my_alias:
                parts.append(f"我叫TA: {my_alias}")
            # Group-level info
            if r["role"]:
                parts.append(f"群内身份: {r['role']}")
            if r["personality"]:
                parts.append(f"性格: {r['personality']}")
            if r["style_notes"]:
                parts.append(f"说话风格: {r['style_notes']}")
            # Contact-level info (merged)
            if r["relationship"]:
                parts.append(f"与我的关系: {r['relationship']}")
            if r["persona_summary"]:
                parts.append(f"人物画像: {r['persona_summary']}")
            if r["style_summary"]:
                parts.append(f"TA的聊天风格: {r['style_summary']}")
            if r["interaction_style_summary"]:
                parts.append(f"互动偏好: {r['interaction_style_summary']}")
            if r["notes"]:
                parts.append(f"备注: {r['notes']}")
            if parts:
                lines.append(f"- {name}: {'; '.join(parts)}")
        lines.append("")
        return "\n".join(lines) + "\n"

    def _resolve_sender(self, wxid: str) -> str:
        """Try to resolve wxid to a display name."""
        contact = self._context.get_contact(wxid)
        if contact:
            return contact.remark or contact.nickname or wxid
        return wxid

    # ── helpers ───────────────────────────────────────────────────

    def _get_client_and_model(self) -> tuple[anthropic.Anthropic, str]:
        """Get API client and model, reading DB config with env var fallback."""
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
            or self._chat_model
        )
        client = anthropic.Anthropic(
            api_key=api_key,
            base_url=base_url or None,
        )
        return client, model

    def _clean_response(
        self, text: str, *, contact_id: str | None = None, group_id: str | None = None,
    ) -> str:
        patterns = self._style_manager.get_forbidden_patterns(
            contact_id=contact_id, group_id=group_id,
        )
        for pattern in patterns:
            text = text.replace(pattern, "")
        return text.strip()

    def _ensure_records(self, msg: IncomingMessage) -> None:
        """Auto-create contact/group DB records for new senders."""
        import re

        # Skip invalid wxids (pure numbers)
        if re.fullmatch(r"\d+", msg.sender_id):
            return

        # Ensure contact exists
        if not self._context.get_contact(msg.sender_id):
            from src.models.schemas import Contact as ContactModel
            self._context.save_contact(ContactModel(
                wxid=msg.sender_id,
                nickname=msg.sender_name,
                is_whitelist=False,
            ))
            logger.info("Auto-created contact: {} ({})", msg.sender_name, msg.sender_id)

        # Ensure group exists
        if msg.is_group and msg.group_id:
            from src.models.schemas import Group as GroupModel
            if not self._context.get_group(msg.group_id):
                self._context.save_group(GroupModel(
                    group_id=msg.group_id,
                    group_name=msg.group_name,
                    is_active=False,
                ))
                logger.info("Auto-created group: {} ({})", msg.group_name, msg.group_id)

            # Track group member
            from datetime import datetime as dt
            self._context._conn.execute(
                """INSERT INTO group_members (group_id, wxid, nickname, msg_count, last_msg_at)
                   VALUES (?, ?, ?, 1, ?)
                   ON CONFLICT(group_id, wxid) DO UPDATE SET
                   nickname = excluded.nickname,
                   msg_count = msg_count + 1,
                   last_msg_at = excluded.last_msg_at""",
                (msg.group_id, msg.sender_id, msg.sender_name, dt.now().isoformat()),
            )
            self._context._conn.commit()

    def _handle_pause(self, msg: IncomingMessage) -> None:
        contact = self._context.get_contact(msg.sender_id)
        if contact:
            contact.is_paused = True
            self._context.save_contact(contact)
            logger.info("Paused auto-reply for {} (manual takeover)", msg.sender_name)
