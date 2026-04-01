import pytest

from src.control.repositories.review_repository import ReviewRepository
from src.core.context import ContextManager


def test_create_and_get_item(tmp_path):
    ctx = ContextManager(tmp_path / "test.db")
    repo = ReviewRepository(ctx)

    item = repo.create_item(
        review_type="rule_change",
        target_type="contact",
        target_id="wxid_1",
        analysis_run_id=1,
        proposed_payload={"chat_rules": {"tone": "随意"}},
        rationale={"reason": "test"},
    )
    assert item["status"] == "pending"
    fetched = repo.get_item(item["id"])
    assert fetched["target_id"] == "wxid_1"


def test_list_pending_items(tmp_path):
    ctx = ContextManager(tmp_path / "test.db")
    repo = ReviewRepository(ctx)

    repo.create_item(review_type="rule_change", target_type="contact", target_id="wxid_1",
                     proposed_payload={"tone": "随意"})
    repo.create_item(review_type="rule_change", target_type="group", target_id="g1",
                     proposed_payload={"tone": "轻松"})

    items, total = repo.list_items(status="pending")
    assert total == 2


def test_mark_applied(tmp_path):
    ctx = ContextManager(tmp_path / "test.db")
    repo = ReviewRepository(ctx)

    item = repo.create_item(review_type="rule_change", target_type="contact", target_id="wxid_1",
                            proposed_payload={"tone": "随意"})
    repo.mark_applied(item["id"])
    fetched = repo.get_item(item["id"])
    assert fetched["status"] == "applied"
    assert fetched["applied_at"] is not None


def test_mark_applied_with_edited_payload(tmp_path):
    ctx = ContextManager(tmp_path / "test.db")
    repo = ReviewRepository(ctx)

    item = repo.create_item(review_type="rule_change", target_type="contact", target_id="wxid_1",
                            proposed_payload={"tone": "随意"})
    edited = {"tone": "更随意"}
    repo.mark_applied(item["id"], edited_payload=edited)
    fetched = repo.get_item(item["id"])
    assert fetched["status"] == "applied"
    assert fetched["edited_payload_json"] is not None


def test_mark_rejected(tmp_path):
    ctx = ContextManager(tmp_path / "test.db")
    repo = ReviewRepository(ctx)

    item = repo.create_item(review_type="rule_change", target_type="contact", target_id="wxid_1",
                            proposed_payload={"tone": "随意"})
    repo.mark_rejected(item["id"])
    assert repo.get_item(item["id"])["status"] == "rejected"


def test_apply_already_applied_raises(tmp_path):
    ctx = ContextManager(tmp_path / "test.db")
    repo = ReviewRepository(ctx)

    item = repo.create_item(review_type="rule_change", target_type="contact", target_id="wxid_1",
                            proposed_payload={"tone": "随意"})
    repo.mark_applied(item["id"])
    with pytest.raises(ValueError, match="not pending"):
        repo.mark_applied(item["id"])


def test_count_pending(tmp_path):
    ctx = ContextManager(tmp_path / "test.db")
    repo = ReviewRepository(ctx)

    repo.create_item(review_type="rule_change", target_type="contact", target_id="wxid_1",
                     proposed_payload={"tone": "随意"})
    repo.create_item(review_type="rule_change", target_type="contact", target_id="wxid_2",
                     proposed_payload={"tone": "随意"})
    assert repo.count_pending() == 2

    items, _ = repo.list_items()
    repo.mark_applied(items[0]["id"])
    assert repo.count_pending() == 1


def test_increment_error(tmp_path):
    ctx = ContextManager(tmp_path / "test.db")
    repo = ReviewRepository(ctx)

    item = repo.create_item(review_type="rule_change", target_type="contact", target_id="wxid_1",
                            proposed_payload={"tone": "随意"})
    repo.increment_error(item["id"], "write failed")
    fetched = repo.get_item(item["id"])
    assert fetched["apply_attempts"] == 1
    assert fetched["last_error"] == "write failed"
