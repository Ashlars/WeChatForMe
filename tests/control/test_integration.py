import json
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.control.api.app import create_control_app
from src.control.services.analysis_service import AnalysisService
from src.core.context import ContextManager
from src.models.schemas import Contact, Message, MessageDirection


MOCK_OUTPUT = json.dumps({
    "persona_summary": "友善的人",
    "native_style_summary": "口语化",
    "preferred_interaction_style": "轻松",
    "relationship_notes": [],
    "recommended_rule_changes": [],
    "recommended_profile_changes": [
        {"target_type": "contact", "field": "relationship", "value": "好朋友", "reason": "聊天分析"}
    ],
    "recommended_state_changes": [
        {"field": "is_whitelist", "value": True, "reason": "活跃用户"}
    ],
    "confidence": 0.9,
    "evidence": [],
}, ensure_ascii=False)


def test_full_analysis_review_apply_flow(tmp_path):
    db_path = tmp_path / "test.db"
    style_dir = tmp_path / "styles"
    style_dir.mkdir()
    (style_dir / "default.yaml").write_text("chat_rules:\n  tone: 随意\n")

    # Setup data
    ctx = ContextManager(db_path)
    ctx.save_contact(Contact(wxid="wxid_1", nickname="张三"))
    ctx.save_message(Message(
        msg_id="m1", contact_id="wxid_1", direction=MessageDirection.INCOMING, content="你好",
    ))
    ctx.close()

    # Create app
    app = create_control_app(db_path=str(db_path), style_dir=str(style_dir))
    client = TestClient(app)

    # Mock Claude API
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=MOCK_OUTPUT)]
    mock_client.messages.create.return_value = mock_response

    # Run analysis
    analysis_service = AnalysisService(
        app.state.context, style_dir=str(style_dir), client=mock_client,
    )
    run = analysis_service.run_analysis(
        target_type="contact", target_id="wxid_1", trigger_type="manual",
    )
    assert run["status"] == "succeeded"

    # Check reviews were created
    reviews = client.get("/api/reviews?status=pending")
    assert reviews.json()["total"] >= 2

    # Approve the state change (is_whitelist)
    items = reviews.json()["items"]
    state_change = next(i for i in items if i["review_type"] == "contact_state_change")
    resp = client.post(f"/api/reviews/{state_change['id']}/approve")
    assert resp.status_code == 200

    # Verify whitelist was applied
    contact = client.get("/api/contacts/wxid_1")
    assert contact.json()["is_whitelist"] is True

    # Check dashboard reflects changes
    dashboard = client.get("/api/dashboard/summary")
    assert dashboard.json()["whitelist_count"] >= 1
    assert dashboard.json()["analysis_success_24h"] >= 1
