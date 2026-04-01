from fastapi.testclient import TestClient

from src.control.api.app import create_control_app
from src.control.repositories.event_repository import EventRepository
from src.core.context import ContextManager


def test_runtime_status(tmp_path):
    style_dir = tmp_path / "styles"
    style_dir.mkdir()
    (style_dir / "default.yaml").write_text("chat_rules:\n  tone: 随意\n")

    app = create_control_app(db_path=str(tmp_path / "test.db"), style_dir=str(style_dir))
    client = TestClient(app)

    resp = client.get("/api/runtime/status")
    assert resp.status_code == 200
    assert "console_process" in resp.json()


def test_runtime_events(tmp_path):
    db_path = tmp_path / "test.db"
    style_dir = tmp_path / "styles"
    style_dir.mkdir()
    (style_dir / "default.yaml").write_text("chat_rules:\n  tone: 随意\n")

    ctx = ContextManager(db_path)
    event_repo = EventRepository(ctx)
    event_repo.log("test_event", "info", "Test message")
    ctx.close()

    app = create_control_app(db_path=str(db_path), style_dir=str(style_dir))
    client = TestClient(app)

    resp = client.get("/api/runtime/events")
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1
