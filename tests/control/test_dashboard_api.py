from fastapi.testclient import TestClient

from src.control.api.app import create_control_app
from src.core.context import ContextManager
from src.models.schemas import Contact, Group


def test_dashboard_summary_full(tmp_path):
    db_path = tmp_path / "test.db"
    style_dir = tmp_path / "styles"
    style_dir.mkdir()
    (style_dir / "default.yaml").write_text("chat_rules:\n  tone: 随意\n")

    ctx = ContextManager(db_path)
    ctx.save_contact(Contact(wxid="wxid_1", nickname="张三", is_whitelist=True))
    ctx.save_group(Group(group_id="g1", group_name="测试群", is_active=True))
    ctx.close()

    app = create_control_app(db_path=str(db_path), style_dir=str(style_dir))
    client = TestClient(app)

    resp = client.get("/api/dashboard/summary")
    data = resp.json()
    assert resp.status_code == 200
    assert data["whitelist_count"] == 1
    assert data["active_group_count"] == 1
    assert data["pending_review_count"] == 0
    assert data["runtime_status"] == "running"
