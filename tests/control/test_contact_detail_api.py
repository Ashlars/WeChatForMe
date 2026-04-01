from fastapi.testclient import TestClient

from src.control.api.app import create_control_app
from src.core.context import ContextManager
from src.models.schemas import Contact, Group


def test_get_contact_detail(tmp_path):
    db_path = tmp_path / "test.db"
    style_dir = tmp_path / "styles"
    style_dir.mkdir()
    (style_dir / "default.yaml").write_text("chat_rules:\n  tone: 随意\n")

    ctx = ContextManager(db_path)
    ctx.save_contact(Contact(wxid="wxid_1", nickname="张三", relationship="朋友"))
    ctx.close()

    app = create_control_app(db_path=str(db_path), style_dir=str(style_dir))
    client = TestClient(app)

    resp = client.get("/api/contacts/wxid_1")
    assert resp.status_code == 200
    assert resp.json()["nickname"] == "张三"


def test_get_contact_not_found(tmp_path):
    style_dir = tmp_path / "styles"
    style_dir.mkdir()
    (style_dir / "default.yaml").write_text("chat_rules:\n  tone: 随意\n")

    app = create_control_app(db_path=str(tmp_path / "test.db"), style_dir=str(style_dir))
    client = TestClient(app)

    resp = client.get("/api/contacts/nonexistent")
    assert resp.status_code == 404


def test_get_group_detail(tmp_path):
    db_path = tmp_path / "test.db"
    style_dir = tmp_path / "styles"
    style_dir.mkdir()
    (style_dir / "default.yaml").write_text("chat_rules:\n  tone: 随意\n")

    ctx = ContextManager(db_path)
    ctx.save_group(Group(group_id="g1", group_name="测试群", is_active=True))
    ctx.close()

    app = create_control_app(db_path=str(db_path), style_dir=str(style_dir))
    client = TestClient(app)

    resp = client.get("/api/groups/g1")
    assert resp.status_code == 200
    assert resp.json()["group_name"] == "测试群"
