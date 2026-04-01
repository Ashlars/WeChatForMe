from fastapi.testclient import TestClient

from src.control.api.app import create_control_app


def test_create_control_app_exposes_dashboard_summary():
    app = create_control_app(db_path=":memory:", style_dir="styles")
    client = TestClient(app)

    response = client.get("/api/dashboard/summary")

    assert response.status_code == 200
    assert response.json()["runtime_status"] == "running"
