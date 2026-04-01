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


@router.post("/self-analyze")
def self_analyze(request: Request) -> dict:
    """Analyze the user's own messages to auto-update persona profile."""
    import json as json_mod
    import os

    import anthropic

    ctx = request.app.state.context

    # First try: get real human messages from our DB
    rows = ctx._conn.execute(
        """SELECT content, group_id, created_at FROM messages
           WHERE direction = 'outgoing'
           AND (is_ai_generated = 0 OR is_ai_generated IS NULL)
           AND agent_model IS NULL
           AND msg_id NOT LIKE 'out_%'
           AND msg_id NOT LIKE 'proactive_%'
           AND length(content) > 2
           ORDER BY created_at DESC LIMIT 100""",
    ).fetchall()

    # Fallback: read from WeChat encrypted DB directly
    if not rows:
        try:
            rows = _fetch_self_messages_from_wechat()
        except Exception as e:
            return {"error": f"没有足够的真人消息，且无法读取微信数据库: {e}", "updated": False}

    if not rows:
        return {"error": "没有足够的真人消息用于分析", "updated": False}

    messages_text = "\n".join(
        f"{'[群聊]' if r['group_id'] else '[私聊]'} {r['content']}"
        for r in rows
    )

    prompt = f"""分析以下微信聊天记录（全部是同一个人发的），提取这个人的性格、说话风格、习惯等特征。

聊天记录（共 {len(rows)} 条）:
{messages_text}

请返回以下 JSON 格式:
{{
  "user_personality": "性格特点（如：幽默、毒舌、随和）",
  "user_speaking_style": "说话风格（如：口语化、喜欢反问、简短直接）",
  "user_habits": "口头禅和习惯用语（如：喜欢用😂、爱说'绝了'）",
  "user_topics": "感兴趣的话题领域",
  "user_tone": "语气特征（如：轻松、调侃、不正经）",
  "user_extra": "其他显著特征"
}}

要求：
- 从实际聊天内容中归纳，不要编造
- 描述要具体，有例子支撑
- 每个字段用简短的中文描述"""

    # Get API config
    api_key = (
        ctx.get_config("analysis_api_key", "")
        or ctx.get_config("chat_api_key", "")
        or os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
        or os.environ.get("ANTHROPIC_API_KEY", "")
    )
    base_url = (
        ctx.get_config("analysis_api_base_url", "")
        or ctx.get_config("chat_api_base_url", "")
        or os.environ.get("ANTHROPIC_BASE_URL", None)
    )
    model = (
        ctx.get_config("analysis_api_model", "")
        or ctx.get_config("chat_api_model", "")
        or os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL", "")
        or "claude-sonnet-4-6"
    )

    try:
        client = anthropic.Anthropic(api_key=api_key, base_url=base_url or None)
        response = client.messages.create(
            model=model,
            max_tokens=1000,
            system="你是一个聊天风格分析专家。分析用户的聊天记录，提取人格特征。必须返回严格的 JSON。",
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        # Strip markdown fences
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
        parsed = json_mod.loads(raw.strip())

        # Update profile
        updated_fields = []
        for key in ["user_personality", "user_speaking_style", "user_habits", "user_topics", "user_tone", "user_extra"]:
            if key in parsed and parsed[key]:
                ctx.set_config(key, parsed[key])
                updated_fields.append(key)

        return {
            "updated": True,
            "updated_fields": updated_fields,
            "analysis": parsed,
            "messages_analyzed": len(rows),
        }
    except Exception as e:
        return {"error": str(e), "updated": False}


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
