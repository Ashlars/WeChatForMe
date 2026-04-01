from fastapi.testclient import TestClient

from src.control.api.app import create_control_app
from src.core.context import ContextManager
from src.models.schemas import Group, TriggerMode


def test_groups_api_lists_and_updates_trigger_mode(tmp_path):
    db_path = tmp_path / "test.db"
    ctx = ContextManager(db_path)
    ctx.save_group(Group(
        group_id="group_1",
        group_name="测试群",
        is_active=True,
        trigger_mode=TriggerMode.AT_ME,
        keywords=["小明"],
    ))
    ctx.close()

    app = create_control_app(db_path=str(db_path), style_dir="styles")
    client = TestClient(app)

    response = client.get("/api/groups")
    assert response.status_code == 200
    assert response.json()["items"][0]["group_id"] == "group_1"

    patch = client.patch("/api/groups/group_1", json={
        "trigger_mode": "all",
        "keywords": ["小明", "帮忙"],
    })
    assert patch.status_code == 200
    assert patch.json()["trigger_mode"] == "all"
