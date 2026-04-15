from __future__ import annotations

import os
import signal
from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel

from src.control.repositories.event_repository import EventRepository
from src.control.schemas.api import PaginatedResponse


router = APIRouter()

PID_FILE = Path(__file__).resolve().parents[4] / "data" / "runtime.pid"


def _fetch_self_messages_from_wechat() -> list[dict]:
    """Read user's own sent messages from WeChat encrypted DB."""
    import json as json_mod
    import sqlite3

    from src.backend.macos.message_monitor import decrypt_db_to_file

    keys_path = Path("data/wechat_keys.json")
    if not keys_path.exists():
        return []

    with open(keys_path) as f:
        keys = json_mod.load(f)

    # Find DB dir
    base = Path.home() / "Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files"
    db_dir = None
    for entry in base.iterdir():
        candidate = entry / "db_storage"
        if candidate.is_dir():
            db_dir = candidate
            break
    if not db_dir:
        return []

    # Collect self-sent messages from all message DBs
    all_msgs = []
    for db_rel, key_info in keys.items():
        if not db_rel.startswith("message/message_") or "fts" in db_rel or "resource" in db_rel:
            continue

        db_file = db_rel.split("/")[1]
        db_path = db_dir / "message" / db_file
        if not db_path.exists():
            continue

        out_path = f"/tmp/wechat_agent_cache/{db_file.replace('.db', '_analyze.db')}"
        try:
            decrypt_db_to_file(str(db_path), key_info["enc_key"], out_path)
            conn = sqlite3.connect(out_path)
            conn.row_factory = sqlite3.Row

            # Find all Msg_ tables
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'Msg_%'"
            ).fetchall()

            for t in tables:
                try:
                    # local_type=1 is text, self-sent messages have no "wxid:\n" prefix in groups
                    # In private chats, outgoing messages don't have a sender prefix either
                    # We look for messages where real_sender_id is empty (self-sent)
                    # real_sender_id = 1 means self-sent in WeChat DB
                    rows = conn.execute(
                        f"""SELECT message_content, create_time FROM [{t['name']}]
                            WHERE local_type = 1
                            AND real_sender_id = 1
                            AND length(message_content) > 2
                            ORDER BY create_time DESC LIMIT 20""",
                    ).fetchall()
                    for r in rows:
                        content = r["message_content"]
                        if isinstance(content, bytes):
                            continue
                        all_msgs.append({
                            "content": str(content),
                            "group_id": None,
                            "created_at": str(r["create_time"]),
                        })
                except Exception:
                    continue
            conn.close()
        except Exception:
            continue

    # Sort by time, take latest 100
    all_msgs.sort(key=lambda x: x["created_at"], reverse=True)
    return all_msgs[:100]


def _check_runtime_process() -> str:
    """Check if the message runtime process is alive via PID file."""
    if not PID_FILE.exists():
        return "stopped"
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0)  # signal 0 = check if process exists
        return "running"
    except (ValueError, ProcessLookupError, PermissionError):
        return "stopped"


@router.get("/status")
def get_runtime_status(request: Request) -> dict:
    ctx = request.app.state.context
    return {
        "runtime_process": _check_runtime_process(),
        "console_process": "running",
        "auto_reply_enabled": ctx.get_config("auto_reply_enabled", "1") == "1",
        "ai_label_enabled": ctx.get_config("ai_label_enabled", "0") == "1",
        "ai_label_text": ctx.get_config("ai_label_text", "[AI]"),
        "last_rule_reload_at": None,
        "last_batch_analysis_at": None,
    }


class AiLabelToggle(BaseModel):
    enabled: bool | None = None
    label_text: str | None = None


@router.put("/ai-label")
def set_ai_label(body: AiLabelToggle, request: Request) -> dict:
    ctx = request.app.state.context
    if body.enabled is not None:
        ctx.set_config("ai_label_enabled", "1" if body.enabled else "0")
    if body.label_text is not None:
        ctx.set_config("ai_label_text", body.label_text)
    return {
        "ai_label_enabled": ctx.get_config("ai_label_enabled", "0") == "1",
        "ai_label_text": ctx.get_config("ai_label_text", "[AI]"),
    }


class AutoReplyToggle(BaseModel):
    enabled: bool


@router.put("/auto-reply")
def set_auto_reply(body: AutoReplyToggle, request: Request) -> dict:
    ctx = request.app.state.context
    ctx.set_config("auto_reply_enabled", "1" if body.enabled else "0")
    return {"auto_reply_enabled": body.enabled}


USER_PROFILE_KEYS = [
    ("user_nickname", "你的昵称/称呼"),
    ("user_aliases", "别人对你的称呼（多个用逗号隔开）"),
    ("user_personality", "性格特点"),
    ("user_speaking_style", "说话风格"),
    ("user_habits", "口头禅和习惯"),
    ("user_topics", "感兴趣的话题"),
    ("user_tone", "语气特征"),
    ("user_extra", "其他人设补充"),
]


@router.get("/user-profile")
def get_user_profile(request: Request) -> dict:
    ctx = request.app.state.context
    return {key: ctx.get_config(key, "") for key, _ in USER_PROFILE_KEYS}


class UserProfileUpdate(BaseModel):
    user_nickname: str | None = None
    user_aliases: str | None = None
    user_personality: str | None = None
    user_speaking_style: str | None = None
    user_habits: str | None = None
    user_topics: str | None = None
    user_tone: str | None = None
    user_extra: str | None = None


@router.put("/user-profile")
def update_user_profile(body: UserProfileUpdate, request: Request) -> dict:
    ctx = request.app.state.context
    changes = body.model_dump(exclude_none=True)
    for key, value in changes.items():
        ctx.set_config(key, value)
    return {key: ctx.get_config(key, "") for key, _ in USER_PROFILE_KEYS}


def _get_analysis_client(ctx):
    """Get API client for analysis."""
    from src.core.llm import get_client_and_model
    return get_client_and_model(ctx, prefix="analysis")


def _call_llm_json(client, model, system: str, prompt: str) -> dict:
    """Call LLM and parse JSON response."""
    from src.core.llm import parse_llm_json
    raw = client.create_message(model=model, max_tokens=1500, system=system,
                                messages=[{"role": "user", "content": prompt}])
    return parse_llm_json(raw)


def _get_wechat_messages_by_chat(ctx) -> dict[str, list[str]]:
    """Get real human messages grouped by chat (group_id or 'private')."""
    try:
        all_msgs = _fetch_self_messages_from_wechat()
    except Exception:
        all_msgs = []

    if not all_msgs:
        return {}

    # WeChat messages don't have group_id, so return as 'all'
    return {"_all": [m["content"] for m in all_msgs]}


@router.post("/self-analyze")
def self_analyze(request: Request) -> dict:
    """Analyze messages: global persona (fixed traits only) + per-chat context."""
    ctx = request.app.state.context

    # Collect messages from WeChat DB
    try:
        all_msgs = _fetch_self_messages_from_wechat()
    except Exception as e:
        return {"error": f"无法读取微信数据库: {e}", "updated": False}

    if not all_msgs:
        return {"error": "没有足够的真人消息用于分析", "updated": False}

    client, model = _get_analysis_client(ctx)
    all_text = "\n".join(m["content"] for m in all_msgs[:100])

    # ── Step 1: Global persona — only FIXED traits across all chats ──
    global_prompt = f"""分析以下微信聊天记录（全部是同一个人在不同聊天中发的），提取这个人**在所有场合都一致的固有特征**。

聊天记录（共 {len(all_msgs[:100])} 条，来自不同的群聊和私聊）:
{all_text}

请返回以下 JSON 格式:
{{
  "user_personality": "在所有场合都一致的性格特点",
  "user_speaking_style": "所有聊天中都有的说话风格（如：口语化、简短直接）",
  "user_habits": "所有聊天中都用的口头禅和表情（如：😂、绝了）",
  "user_topics": "不要填，留空字符串",
  "user_tone": "所有场合都一致的语气基调",
  "user_extra": "其他所有场合都有的固有特征"
}}

要求：
- 只提取在所有聊天中都一致的特征，不要把某个特定场景的行为当成固有特征
- 比如只在某个群聊足球、只在某个群玩游戏，这些不是固有特征，不要写
- user_topics 留空，话题因聊天对象不同而不同，不是固有的
- 描述要具体"""

    try:
        parsed = _call_llm_json(client, model,
            "你是聊天风格分析专家。只提取跨所有场合一致的固有特征。必须返回严格的 JSON。",
            global_prompt)

        # Force topics to empty
        parsed["user_topics"] = ""

        updated_fields = []
        for key in ["user_personality", "user_speaking_style", "user_habits", "user_topics", "user_tone", "user_extra"]:
            if key in parsed:
                ctx.set_config(key, parsed[key])
                updated_fields.append(key)

    except Exception as e:
        return {"error": f"全局分析失败: {e}", "updated": False}

    # ── Step 2: Per-chat analysis — topics and behavior specific to each chat ──
    # Get active groups with enough messages
    groups = ctx._conn.execute(
        """SELECT g.group_id, g.group_name,
                  (SELECT COUNT(*) FROM messages m WHERE m.group_id = g.group_id) as msg_count
           FROM groups g
           WHERE g.is_active = 1
           ORDER BY msg_count DESC""",
    ).fetchall()

    chat_results = []
    for g in groups:
        if g["msg_count"] < 5:
            continue

        # Get recent messages from this group
        group_msgs = ctx._conn.execute(
            """SELECT contact_id, direction, content FROM messages
               WHERE group_id = ? AND length(content) > 2
               ORDER BY created_at DESC LIMIT 50""",
            (g["group_id"],),
        ).fetchall()

        if len(group_msgs) < 5:
            continue

        group_text = "\n".join(
            f"[{'我' if m['direction'] == 'outgoing' else '对方'}] {m['content']}"
            for m in group_msgs
        )

        chat_prompt = f"""以下是微信群「{g['group_name']}」的聊天记录。分析「我」在这个群里聊什么话题、不聊什么、有什么特别的行为。

聊天记录:
{group_text}

返回一段简短描述（50字以内），格式如：
"在这个群主要聊xxx和xxx，不聊xxx，语气偏xxx"

只输出描述文本，不要JSON，不要引号。"""

        try:
            context_text = client.create_message(
                model=model, max_tokens=2000,
                system="分析用户在特定群聊中的行为特征。只输出描述文本。",
                messages=[{"role": "user", "content": chat_prompt}],
            ).strip('"').strip("'")

            if context_text and len(context_text) > 5:
                # Only update if no manual persona_context already set
                existing = ctx._conn.execute(
                    "SELECT persona_context FROM groups WHERE group_id = ?",
                    (g["group_id"],),
                ).fetchone()

                if not existing or not existing["persona_context"]:
                    ctx._conn.execute(
                        "UPDATE groups SET persona_context = ? WHERE group_id = ?",
                        (context_text, g["group_id"]),
                    )
                    ctx._conn.commit()
                    chat_results.append({
                        "chat": g["group_name"],
                        "context": context_text,
                    })
        except Exception:
            continue

    return {
        "updated": True,
        "updated_fields": updated_fields,
        "analysis": parsed,
        "messages_analyzed": len(all_msgs[:100]),
        "chat_contexts": chat_results,
        "chats_analyzed": len(chat_results),
    }


API_CONFIG_KEYS = [
    ("chat_api_key", "回复消息 API Key"),
    ("chat_api_base_url", "回复消息 API Base URL"),
    ("chat_api_model", "回复消息模型"),
    ("analysis_api_key", "分析数据 API Key"),
    ("analysis_api_base_url", "分析数据 API Base URL"),
    ("analysis_api_model", "分析数据模型"),
]


@router.get("/api-config")
def get_api_config(request: Request) -> dict:
    ctx = request.app.state.context
    config = {}
    for key, _ in API_CONFIG_KEYS:
        val = ctx.get_config(key, "")
        # Mask API keys for display
        if "api_key" in key and val:
            config[key] = val[:8] + "***" + val[-4:] if len(val) > 12 else "***"
        else:
            config[key] = val
    return config


class ApiConfigUpdate(BaseModel):
    chat_api_key: str | None = None
    chat_api_base_url: str | None = None
    chat_api_model: str | None = None
    analysis_api_key: str | None = None
    analysis_api_base_url: str | None = None
    analysis_api_model: str | None = None


@router.put("/api-config")
def update_api_config(body: ApiConfigUpdate, request: Request) -> dict:
    ctx = request.app.state.context
    changes = body.model_dump(exclude_none=True)
    for key, value in changes.items():
        if value:  # Don't save empty strings
            ctx.set_config(key, value)
    # Return masked config
    return get_api_config(request)


@router.get("/events", response_model=PaginatedResponse)
def list_runtime_events(
    request: Request, page: int = 1, page_size: int = 20,
) -> PaginatedResponse:
    repo = EventRepository(request.app.state.context)
    items, total = repo.list_events(page=page, page_size=page_size)
    return PaginatedResponse(items=items, page=page, page_size=page_size, total=total)
