from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from datetime import datetime as dt

import anthropic
from loguru import logger

from src.backend.base import IncomingMessage, WeChatBackend
from src.core.config import ConfigManager
from src.models.schemas import Contact as ContactModel, Group as GroupModel
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
        # Self-sent messages: save as outgoing, don't trigger reply
        if msg.is_self:
            # For private chats, use the conversation partner's wxid as contact_id
            # so the message shows up in the right conversation history.
            # For groups, use __self__.
            chat_wxid = msg.chat_wxid
            private_contact_id = chat_wxid if (chat_wxid and not msg.is_group) else "__self__"
            self._context.save_message(Message(
                msg_id=msg.msg_id or f"self_{uuid.uuid4().hex[:12]}",
                contact_id="__self__" if msg.is_group else private_contact_id,
                group_id=msg.group_id,
                direction=MessageDirection.OUTGOING,
                content=msg.content,
                created_at=msg.timestamp,
            ))
            # Still ensure group record exists
            if msg.is_group and msg.group_id:

                if not self._context.get_group(msg.group_id):
                    self._context.save_group(GroupModel(
                        group_id=msg.group_id,
                        group_name=msg.group_name,
                        is_active=False,
                    ))
            return

        # Incoming: save and process
        self._context.save_message(Message(
            msg_id=msg.msg_id or f"in_{uuid.uuid4().hex[:12]}",
            contact_id=msg.sender_id,
            group_id=msg.group_id,
            direction=MessageDirection.INCOMING,
            content=msg.content,
            created_at=msg.timestamp,
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
            # Run in background thread to avoid blocking the message monitor
            t = threading.Thread(target=self._do_reply, args=[msg], daemon=True)
            t.start()

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

        target = self._resolve_target(msg)
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
        else:
            logger.error(
                "Failed to send reply to {} (target: '{}'), message lost: {}",
                msg.sender_name, target, reply[:50],
            )
            # Save as failed message for potential manual retry
            self._context.save_message(Message(
                msg_id=f"fail_{uuid.uuid4().hex[:12]}",
                contact_id="__self__" if msg.is_group else msg.sender_id,
                group_id=msg.group_id,
                direction=MessageDirection.OUTGOING,
                content=f"[发送失败] {reply}",
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
            messages = self._build_messages(history, msg.content, is_group=msg.is_group, group_id=msg.group_id)

            client, model = self._get_client_and_model()
            logger.info("Calling API ({}) with {} history messages", model, len(history))
            reply = client.create_message(
                model=model,
                max_tokens=max(max_len * 2, 2000),
                system=system_prompt,
                messages=messages,
            )
            logger.info("LLM replied: {}", reply[:100])
            return self._clean_response(
                reply, contact_id=msg.sender_id, group_id=msg.group_id,
            )
        except Exception:
            logger.exception("Failed to generate reply")
            return None

    def _build_user_persona(self, *, persona_context: str | None = None) -> str:
        from src.core.llm import build_user_persona
        return build_user_persona(self._context, persona_context=persona_context)

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
        user_nick = self._context.get_config("user_nickname", "") or self._user_name

        # Get per-chat persona context
        chat_persona_context = None
        if is_group and group_id:
            group_obj = self._context.get_group(group_id)
            if group_obj and group_obj.persona_context:
                chat_persona_context = group_obj.persona_context
        elif contact and contact.persona_context:
            chat_persona_context = contact.persona_context

        user_persona = self._build_user_persona(persona_context=chat_persona_context)

        # AI label context — let the model know what the label means
        ai_label_hint = ""
        if self._context.get_config("ai_label_enabled", "0") == "1":
            label_text = self._context.get_config("ai_label_text", "[AI]")
            ai_label_hint = f"\n注意：你发送的消息前面会被自动加上「{label_text}」标识，这是系统加的，你不需要自己加。如果聊天记录里看到带「{label_text}」前缀的消息，那就是你之前说的话。\n"

        if is_group:
            members_prompt = self._build_members_prompt(group_id) if group_id else ""
            user_aliases = self._context.get_config("user_aliases", "")
            alias_warning = ""
            if user_aliases:
                alias_warning = f"\n- 「{user_aliases}」是别人叫你的称呼，绝对不要用这些去叫别人"

            return f"""你是{user_nick}本人，不是AI，不是机器人，不是助手。你就是{user_nick}。
正在微信群「{group_name or '群聊'}」里聊天。不要提及或混入其他群或私聊的内容。

【绝对禁止】
- 绝对不能说自己是AI、机器人、人工智能、语言模型或程序
- 别人问"你是不是AI"、"你是机器人吗"时，根据情况否认、反问或调侃（如"你才是AI"、"我要是AI还能跟你在这扯淡？"）
- 别人问"你是谁"时，用{user_nick}的身份自然回答，可以调侃对方
- 不要说任何暴露AI身份的话（如"作为…"、"我没有感情"、"我的知识截止…"）
{ai_label_hint}
{user_persona}【最重要 — 人物识别与称呼】
- 消息格式为「[昵称] 内容」，不同的昵称是不同的人，绝对不能搞混
- [{user_nick}(你自己)] 开头的是你之前说过的话
- 你必须清楚每条消息是谁说的，不要把 A 说的话当成 B 说的
- 如果成员画像里写了「我叫TA: xxx」，提到这个人时用这个称呼
- 但不是每句话都要叫名字，大部分时候直接说事情就行，像真人一样自然
- 严禁张冠李戴：不要把甲的话当成乙说的{alias_warning}

核心要求：
1. 针对别人刚说的话来回应，不要自说自话
2. 像真人一样接话、附和、反驳、追问
3. 同一个人连发多条消息，当作一段话理解，只回复一条
4. 不需要一条一条对应回复，整体理解后回一条就行
5. 不要每句话都带表情/emoji，大部分时候纯文字就行，偶尔用一个
6. 只输出回复内容，不要任何前缀或标记
7. 一次只回复一条消息，简短自然

{members_prompt}【严格遵守以下聊天规则】:
{style_prompt}"""
        else:
            # Get alias for this contact
            contact_alias = ""
            if contact and contact.my_alias_for:
                contact_alias = f"\n- 你叫对方「{contact.my_alias_for}」，但不用每句话都叫，大部分时候直接说事情"

            return f"""你是{user_nick}本人，不是AI。正在用微信和{relationship}私聊。
不要提及或混入群聊或跟其他人的对话内容。

【绝对禁止】
- 不能说自己是AI、机器人或程序，别人问就否认或调侃
- 不要说暴露AI身份的话
{ai_label_hint}
{user_persona}核心要求：
1. 针对对方刚说的话来回应，不要自说自话
2. 像真人聊天一样，接住对方的话，自然回复
3. 对方连发多条消息当作一段话理解，只回一条
4. 不要每句话都带表情，大部分时候纯文字，偶尔用一个
5. 只输出回复内容，不要任何解释或前缀{contact_alias}

【严格遵守以下聊天规则】:
{style_prompt}"""

    def _build_messages(
        self, history: list[Message], current_content: str, *, is_group: bool = False, group_id: str | None = None,
    ) -> list[dict]:
        """Build messages for API call.

        All messages are shown as a single chronological chat log.
        The model sees who said what, including its own previous replies.
        Newer messages are closer to the end = higher weight.
        """
        messages: list[dict] = []

        if is_group:
            # Batch-resolve all sender names to avoid N+1 queries
            sender_cache: dict[str, str] = {}
            for m in history:
                if m.direction != MessageDirection.OUTGOING and m.contact_id not in sender_cache:
                    sender_cache[m.contact_id] = self._resolve_sender(m.contact_id, group_id=group_id)

            def format_msg(msg: Message) -> str:
                if msg.direction == MessageDirection.OUTGOING:
                    return f"[{self._user_name}(你自己)] {msg.content}"
                return f"[{sender_cache.get(msg.contact_id, msg.contact_id)}] {msg.content}"

            all_lines = [format_msg(m) for m in history]

            if all_lines:
                last_our_idx = -1
                for i, msg in enumerate(history):
                    if msg.direction == MessageDirection.OUTGOING:
                        last_our_idx = i

                new_senders = []
                start = last_our_idx + 1 if last_our_idx >= 0 else 0
                for m in history[start:]:
                    if m.direction != MessageDirection.OUTGOING:
                        name = sender_cache.get(m.contact_id, m.contact_id)
                        if name not in new_senders:
                            new_senders.append(name)

                sender_hint = f"最新发言者: {', '.join(new_senders)}" if new_senders else ""

                messages.append({
                    "role": "user",
                    "content": (
                        f"以下是群聊的完整聊天记录（从旧到新，共{len(all_lines)}条）。"
                        f"方括号里是发言者名字，不同名字是不同的人。"
                        f"带(你自己)的是你之前说的话。\n"
                        f"{sender_hint}\n\n"
                        + "\n".join(all_lines)
                        + "\n\n请根据以上对话，自然地回复最新的消息。"
                    ),
                })
            else:
                messages.append({
                    "role": "user",
                    "content": f"对方刚说了: {current_content}\n请回复。",
                })
        else:
            # Private chat: resolve contact name once, not per message
            other_name = "对方"
            other_ids = {m.contact_id for m in history if m.direction != MessageDirection.OUTGOING}
            if other_ids:
                cobj = self._context.get_contact(next(iter(other_ids)))
                if cobj:
                    other_name = cobj.my_alias_for or cobj.remark or cobj.nickname or "对方"

            all_lines = []
            for msg in history:
                if msg.direction == MessageDirection.OUTGOING:
                    all_lines.append(f"[你] {msg.content}")
                else:
                    all_lines.append(f"[{other_name}] {msg.content}")

            if all_lines:
                messages.append({
                    "role": "user",
                    "content": (
                        f"以下是你和对方的聊天记录（从旧到新，共{len(all_lines)}条）。"
                        f"[你]是你之前说的话，另一个名字是对方。\n\n"
                        + "\n".join(all_lines)
                        + "\n\n请根据以上对话，自然地回复对方最新的消息。"
                    ),
                })
            else:
                messages.append({
                    "role": "user",
                    "content": f"对方刚说了: {current_content}\n请回复。",
                })

        return messages

    def _build_members_prompt(self, group_id: str) -> str:
        """Build a prompt section describing known group members, merging contact data."""
        rows = self._context._conn.execute(
            """SELECT gm.nickname, gm.role, gm.personality, gm.style_notes, gm.notes,
                      gm.my_alias_for AS gm_alias,
                      c.relationship, c.persona_summary, c.style_summary, c.interaction_style_summary,
                      c.my_alias_for AS c_alias, c.remark AS c_remark
               FROM group_members gm
               LEFT JOIN contacts c ON gm.wxid = c.wxid
               WHERE gm.group_id = ?
               AND (gm.role != '' OR gm.personality != '' OR gm.style_notes != '' OR gm.notes != ''
                    OR gm.my_alias_for != '' OR c.my_alias_for IS NOT NULL
                    OR c.relationship IS NOT NULL OR c.persona_summary IS NOT NULL
                    OR c.style_summary IS NOT NULL)""",
            (group_id,),
        ).fetchall()
        if not rows:
            return ""

        lines = ["【群成员画像（根据每个人的特点调整回复方式）】"]
        for r in rows:
            # Resolve display name: prefer alias → remark → nickname
            gm_alias = r["gm_alias"] or ""
            c_alias = r["c_alias"] or ""
            c_remark = r["c_remark"] or ""
            nickname = r["nickname"] or "未知"
            my_name_for = gm_alias or c_alias
            name = c_remark or nickname

            parts = []
            if my_name_for:
                parts.append(f"我叫TA: {my_name_for}")
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

    def _resolve_target(self, msg: IncomingMessage) -> str:
        """Resolve the latest name for sending a message. Always reads from DB to avoid stale names."""
        if msg.is_group and msg.group_id:
            group = self._context.get_group(msg.group_id)
            if group and group.group_name:
                return group.group_name
            return msg.group_name or msg.group_id
        else:
            contact = self._context.get_contact(msg.sender_id)
            if contact:
                return contact.remark or contact.nickname or msg.sender_name
            return msg.sender_name

    def _resolve_sender(self, wxid: str, group_id: str | None = None) -> str:
        """Resolve wxid to display name. Prioritizes: group_member alias → contact alias → remark → nickname."""
        # Check group-specific alias first
        if group_id:
            row = self._context._conn.execute(
                "SELECT my_alias_for, nickname FROM group_members WHERE group_id = ? AND wxid = ?",
                (group_id, wxid),
            ).fetchone()
            if row and row["my_alias_for"]:
                return row["my_alias_for"]

        # Then check contact-level alias
        contact = self._context.get_contact(wxid)
        if contact:
            return contact.my_alias_for or contact.remark or contact.nickname or wxid
        return wxid

    # ── helpers ───────────────────────────────────────────────────

    def _get_client_and_model(self) -> tuple[anthropic.Anthropic, str]:
        from src.core.llm import get_client_and_model
        return get_client_and_model(self._context, prefix="chat", default_model=self._chat_model)

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

        # Skip invalid wxids (pure numbers)
        if re.fullmatch(r"\d+", msg.sender_id):
            return

        # Ensure contact exists, update nickname if changed
        existing_contact = self._context.get_contact(msg.sender_id)
        if not existing_contact:
            self._context.save_contact(ContactModel(
                wxid=msg.sender_id,
                nickname=msg.sender_name,
                is_whitelist=False,
            ))
            logger.info("Auto-created contact: {} ({})", msg.sender_name, msg.sender_id)
        elif msg.sender_name and existing_contact.nickname != msg.sender_name:
            old_nick = existing_contact.nickname
            existing_contact.nickname = msg.sender_name
            self._context.save_contact(existing_contact)
            logger.debug("Updated contact nickname: {} -> {}", old_nick, msg.sender_name)

        # Ensure group exists, update group_name if changed
        if msg.is_group and msg.group_id:
            existing_group = self._context.get_group(msg.group_id)
            if not existing_group:
                self._context.save_group(GroupModel(
                    group_id=msg.group_id,
                    group_name=msg.group_name,
                    is_active=False,
                ))
                logger.info("Auto-created group: {} ({})", msg.group_name, msg.group_id)
            elif msg.group_name and existing_group.group_name != msg.group_name:
                # Group was renamed in WeChat — update our DB
                existing_group.group_name = msg.group_name
                self._context.save_group(existing_group)
                logger.info("Updated group name: {} -> {}", existing_group.group_name, msg.group_name)

            # Track group member
            with self._context._lock:
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
