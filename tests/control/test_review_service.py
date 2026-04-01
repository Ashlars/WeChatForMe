from src.control.repositories.review_repository import ReviewRepository
from src.control.services.review_service import ReviewService
from src.core.context import ContextManager
from src.models.schemas import Contact


def _setup(tmp_path):
    ctx = ContextManager(tmp_path / "test.db")
    style_dir = tmp_path / "styles"
    style_dir.mkdir()
    (style_dir / "default.yaml").write_text("chat_rules:\n  tone: 随意\n")
    ctx.save_contact(Contact(wxid="wxid_1", nickname="张三"))
    return ctx, style_dir


def test_approve_rule_change(tmp_path):
    ctx, style_dir = _setup(tmp_path)
    review_repo = ReviewRepository(ctx)

    item = review_repo.create_item(
        review_type="rule_change",
        target_type="contact",
        target_id="wxid_1",
        proposed_payload={
            "scope_type": "contact",
            "path": "chat_rules.tone",
            "operation": "set",
            "value": "更口语化",
            "reason": "test",
        },
    )

    service = ReviewService(ctx, style_dir=str(style_dir))
    result = service.approve(item["id"])
    assert result["status"] == "applied"


def test_reject_review(tmp_path):
    ctx, style_dir = _setup(tmp_path)
    review_repo = ReviewRepository(ctx)

    item = review_repo.create_item(
        review_type="rule_change", target_type="contact", target_id="wxid_1",
        proposed_payload={"path": "chat_rules.tone", "value": "test"},
    )

    service = ReviewService(ctx, style_dir=str(style_dir))
    result = service.reject(item["id"])
    assert result["status"] == "rejected"


def test_approve_contact_state_change(tmp_path):
    ctx, style_dir = _setup(tmp_path)
    review_repo = ReviewRepository(ctx)

    item = review_repo.create_item(
        review_type="contact_state_change", target_type="contact", target_id="wxid_1",
        proposed_payload={"field": "is_whitelist", "value": True},
    )

    service = ReviewService(ctx, style_dir=str(style_dir))
    service.approve(item["id"])

    contact = ctx.get_contact("wxid_1")
    assert contact.is_whitelist is True


def test_approve_contact_profile_change(tmp_path):
    ctx, style_dir = _setup(tmp_path)
    review_repo = ReviewRepository(ctx)

    item = review_repo.create_item(
        review_type="contact_profile_change", target_type="contact", target_id="wxid_1",
        proposed_payload={"field": "relationship", "value": "好朋友"},
    )

    service = ReviewService(ctx, style_dir=str(style_dir))
    service.approve(item["id"])

    contact = ctx.get_contact("wxid_1")
    assert contact.relationship == "好朋友"


def test_apply_edited(tmp_path):
    ctx, style_dir = _setup(tmp_path)
    review_repo = ReviewRepository(ctx)

    item = review_repo.create_item(
        review_type="contact_state_change", target_type="contact", target_id="wxid_1",
        proposed_payload={"field": "is_whitelist", "value": False},
    )

    service = ReviewService(ctx, style_dir=str(style_dir))
    result = service.apply_edited(item["id"], {"field": "is_whitelist", "value": True})
    assert result["status"] == "applied"

    contact = ctx.get_contact("wxid_1")
    assert contact.is_whitelist is True
