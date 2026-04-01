from fastapi.testclient import TestClient

from src.control.api.app import create_control_app
from src.control.repositories.review_repository import ReviewRepository
from src.core.context import ContextManager
from src.models.schemas import Contact


def _create_test_app(tmp_path):
    db_path = tmp_path / "test.db"
    style_dir = tmp_path / "styles"
    style_dir.mkdir()
    (style_dir / "default.yaml").write_text("chat_rules:\n  tone: 随意\n")

    ctx = ContextManager(db_path)
    ctx.save_contact(Contact(wxid="wxid_1", nickname="张三"))
    review_repo = ReviewRepository(ctx)
    review_repo.create_item(
        review_type="contact_state_change",
        target_type="contact",
        target_id="wxid_1",
        proposed_payload={"field": "is_whitelist", "value": True},
    )
    ctx.close()

    return create_control_app(db_path=str(db_path), style_dir=str(style_dir))


def test_list_reviews(tmp_path):
    app = _create_test_app(tmp_path)
    client = TestClient(app)
    resp = client.get("/api/reviews")
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


def test_approve_review(tmp_path):
    app = _create_test_app(tmp_path)
    client = TestClient(app)
    resp = client.post("/api/reviews/1/approve")
    assert resp.status_code == 200
    assert resp.json()["status"] == "applied"


def test_reject_review(tmp_path):
    app = _create_test_app(tmp_path)
    client = TestClient(app)
    resp = client.post("/api/reviews/1/reject")
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


def test_get_review_not_found(tmp_path):
    app = _create_test_app(tmp_path)
    client = TestClient(app)
    resp = client.get("/api/reviews/999")
    assert resp.status_code == 404
