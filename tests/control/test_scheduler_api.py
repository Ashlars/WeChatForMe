from fastapi.testclient import TestClient

from src.control.api.app import create_control_app


def test_get_default_analysis_policy(tmp_path):
    style_dir = tmp_path / "styles"
    style_dir.mkdir()
    (style_dir / "default.yaml").write_text("chat_rules:\n  tone: 随意\n")

    app = create_control_app(db_path=str(tmp_path / "test.db"), style_dir=str(style_dir))
    client = TestClient(app)

    resp = client.get("/api/scheduler/analysis-policy")
    assert resp.status_code == 200
    data = resp.json()
    assert "enabled" in data
    assert "cron_expr" in data


def test_update_analysis_policy(tmp_path):
    style_dir = tmp_path / "styles"
    style_dir.mkdir()
    (style_dir / "default.yaml").write_text("chat_rules:\n  tone: 随意\n")

    app = create_control_app(db_path=str(tmp_path / "test.db"), style_dir=str(style_dir))
    client = TestClient(app)

    resp = client.put("/api/scheduler/analysis-policy", json={
        "enabled": True,
        "cron_expr": "0 */12 * * *",
        "max_targets_per_run": 10,
    })
    assert resp.status_code == 200
    assert resp.json()["cron_expr"] == "0 */12 * * *"
