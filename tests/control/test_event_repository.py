from src.control.repositories.event_repository import EventRepository
from src.core.context import ContextManager


def test_log_inserts_event(tmp_path):
    ctx = ContextManager(tmp_path / "test.db")
    repo = EventRepository(ctx)

    repo.log("rule_applied", "info", "Rule applied for wxid_1")

    items, total = repo.list_events()
    assert total == 1
    assert items[0]["event_type"] == "rule_applied"
    assert items[0]["level"] == "info"
    assert items[0]["message"] == "Rule applied for wxid_1"


def test_list_events_sorted_desc(tmp_path):
    ctx = ContextManager(tmp_path / "test.db")
    repo = EventRepository(ctx)

    repo.log("first_event", "info", "First")
    repo.log("second_event", "info", "Second")

    items, total = repo.list_events()
    assert total == 2
    assert items[0]["event_type"] == "second_event"  # most recent first


def test_log_with_payload(tmp_path):
    ctx = ContextManager(tmp_path / "test.db")
    repo = EventRepository(ctx)

    repo.log("analysis_failed", "error", "API timeout", payload={"run_id": 1})

    items, _ = repo.list_events()
    assert items[0]["payload_json"] is not None
    assert "run_id" in items[0]["payload_json"]


def test_list_events_pagination(tmp_path):
    ctx = ContextManager(tmp_path / "test.db")
    repo = EventRepository(ctx)

    for i in range(5):
        repo.log(f"event_{i}", "info", f"Message {i}")

    items, total = repo.list_events(page=1, page_size=2)
    assert total == 5
    assert len(items) == 2
