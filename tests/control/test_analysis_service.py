import json
from unittest.mock import MagicMock

from src.control.services.analysis_service import AnalysisService
from src.core.context import ContextManager
from src.models.schemas import Contact, Message, MessageDirection


MOCK_ANALYSIS_OUTPUT = {
    "persona_summary": "随和的人",
    "native_style_summary": "口语化，短句多",
    "preferred_interaction_style": "轻松直接",
    "relationship_notes": ["经常聊日常"],
    "recommended_rule_changes": [
        {
            "scope_type": "contact",
            "path": "chat_rules.tone",
            "operation": "set",
            "value": "更口语化",
            "reason": "对方偏口语风格",
        }
    ],
    "recommended_profile_changes": [
        {
            "target_type": "contact",
            "field": "persona_summary",
            "value": "随和的人",
            "reason": "聊天记录分析",
        }
    ],
    "recommended_state_changes": [],
    "confidence": 0.85,
    "evidence": [
        {
            "message_ids": ["msg_1"],
            "summary": "短句多",
            "observation": "口语化风格",
        }
    ],
}


def _setup(tmp_path):
    ctx = ContextManager(tmp_path / "test.db")
    style_dir = tmp_path / "styles"
    style_dir.mkdir()
    (style_dir / "default.yaml").write_text("chat_rules:\n  tone: 随意\n")

    ctx.save_contact(Contact(wxid="wxid_1", nickname="张三", is_whitelist=True))
    ctx.save_message(Message(
        msg_id="msg_1", contact_id="wxid_1", direction=MessageDirection.INCOMING,
        content="你好啊",
    ))

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps(MOCK_ANALYSIS_OUTPUT, ensure_ascii=False))]
    mock_client.messages.create.return_value = mock_response

    return ctx, style_dir, mock_client


def test_run_contact_analysis(tmp_path):
    ctx, style_dir, mock_client = _setup(tmp_path)

    service = AnalysisService(ctx, style_dir=str(style_dir), client=mock_client)
    run = service.run_analysis(target_type="contact", target_id="wxid_1", trigger_type="manual")

    assert run["status"] == "succeeded"
    assert run["summary"] == "随和的人"
    mock_client.messages.create.assert_called_once()


def test_analysis_creates_review_items(tmp_path):
    ctx, style_dir, mock_client = _setup(tmp_path)

    service = AnalysisService(ctx, style_dir=str(style_dir), client=mock_client)
    service.run_analysis(target_type="contact", target_id="wxid_1", trigger_type="manual")

    pending = ctx._conn.execute(
        "SELECT COUNT(*) AS c FROM review_items WHERE status='pending'"
    ).fetchone()["c"]
    assert pending == 2  # 1 rule_change + 1 profile_change


def test_analysis_updates_profile(tmp_path):
    ctx, style_dir, mock_client = _setup(tmp_path)

    service = AnalysisService(ctx, style_dir=str(style_dir), client=mock_client)
    service.run_analysis(target_type="contact", target_id="wxid_1", trigger_type="manual")

    row = ctx._conn.execute(
        "SELECT persona_summary, style_summary, last_analysis_at FROM contacts WHERE wxid='wxid_1'"
    ).fetchone()
    assert row["persona_summary"] == "随和的人"
    assert row["style_summary"] == "口语化，短句多"
    assert row["last_analysis_at"] is not None


def test_analysis_failure_records_error(tmp_path):
    ctx, style_dir, _ = _setup(tmp_path)

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("API timeout")

    service = AnalysisService(ctx, style_dir=str(style_dir), client=mock_client)
    run = service.run_analysis(target_type="contact", target_id="wxid_1", trigger_type="manual")

    assert run["status"] == "failed"
    assert "API timeout" in run["error_message"]


def test_analysis_logs_events(tmp_path):
    ctx, style_dir, mock_client = _setup(tmp_path)

    service = AnalysisService(ctx, style_dir=str(style_dir), client=mock_client)
    service.run_analysis(target_type="contact", target_id="wxid_1", trigger_type="manual")

    events = ctx._conn.execute("SELECT * FROM runtime_events").fetchall()
    assert len(events) >= 1
    assert any(e["event_type"] == "analysis_succeeded" for e in events)
