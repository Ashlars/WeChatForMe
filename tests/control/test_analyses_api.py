from fastapi.testclient import TestClient

from src.control.api.app import create_control_app
from src.core.context import ContextManager
from src.models.schemas import Contact, Message, MessageDirection


def test_list_analysis_runs_empty(tmp_path):
    style_dir = tmp_path / "styles"
    style_dir.mkdir()
    (style_dir / "default.yaml").write_text("chat_rules:\n  tone: 随意\n")

    app = create_control_app(db_path=str(tmp_path / "test.db"), style_dir=str(style_dir))
    client = TestClient(app)
    resp = client.get("/api/analysis-runs")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_get_analysis_run_not_found(tmp_path):
    style_dir = tmp_path / "styles"
    style_dir.mkdir()
    (style_dir / "default.yaml").write_text("chat_rules:\n  tone: 随意\n")

    app = create_control_app(db_path=str(tmp_path / "test.db"), style_dir=str(style_dir))
    client = TestClient(app)
    resp = client.get("/api/analysis-runs/999")
    assert resp.status_code == 404
