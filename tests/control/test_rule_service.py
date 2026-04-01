from src.control.repositories.rule_repository import RuleRepository
from src.core.context import ContextManager


def test_insert_rule_version_marks_only_one_active(tmp_path):
    ctx = ContextManager(tmp_path / "test.db")
    repo = RuleRepository(ctx)

    first = repo.create_rule_version(
        scope_type="contact",
        scope_id="wxid_1",
        source="manual",
        document={"metadata": {}, "chat_rules": {"tone": "随意"}},
    )
    second = repo.create_rule_version(
        scope_type="contact",
        scope_id="wxid_1",
        source="manual",
        document={"metadata": {}, "chat_rules": {"tone": "更随意"}},
    )

    active = repo.get_active_rule("contact", "wxid_1")

    assert first["version"] == 1
    assert second["version"] == 2
    assert active["version"] == 2
