from fastapi.testclient import TestClient

from src.control.api.app import create_control_app
from src.core.context import ContextManager
from src.models.schemas import Contact


def test_contacts_api_lists_and_updates_whitelist(tmp_path):
    db_path = tmp_path / "test.db"
    ctx = ContextManager(db_path)
    ctx.save_contact(Contact(wxid="wxid_1", nickname="张三", is_whitelist=False))
    ctx.close()

    app = create_control_app(db_path=str(db_path), style_dir="styles")
    client = TestClient(app)

    response = client.get("/api/contacts")
    assert response.status_code == 200
    assert response.json()["items"][0]["wxid"] == "wxid_1"

    patch = client.patch("/api/contacts/wxid_1", json={"is_whitelist": True})
    assert patch.status_code == 200
    assert patch.json()["is_whitelist"] is True
