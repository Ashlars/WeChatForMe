from fastapi.testclient import TestClient

from src.control.api.app import create_control_app


def test_rules_api_reads_and_updates_contact_rule(tmp_path):
    style_dir = tmp_path / "styles"
    style_dir.mkdir()

    app = create_control_app(db_path=str(tmp_path / "test.db"), style_dir=str(style_dir))
    client = TestClient(app)

    put_response = client.put("/api/rules/private/wxid_1", json={
        "document": {
            "metadata": {"description": "朋友"},
            "chat_rules": {"tone": "自然", "reply_length": "1-2句"},
        }
    })
    assert put_response.status_code == 200
    assert put_response.json()["document"]["chat_rules"]["tone"] == "自然"

    get_response = client.get("/api/rules/private/wxid_1")
    assert get_response.status_code == 200
    assert get_response.json()["version"] == 1
