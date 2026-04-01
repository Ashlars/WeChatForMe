import yaml

from src.control.bootstrap import bootstrap_rules_if_empty
from src.control.repositories.rule_repository import RuleRepository
from src.core.context import ContextManager


def test_bootstrap_imports_default_and_group_styles(tmp_path):
    style_dir = tmp_path / "styles"
    (style_dir / "groups").mkdir(parents=True)

    (style_dir / "default.yaml").write_text(
        yaml.dump({"chat_rules": {"tone": "自然"}}, allow_unicode=True),
        encoding="utf-8",
    )
    (style_dir / "groups" / "demo.yaml").write_text(
        yaml.dump(
            {
                "group_id": "group_demo",
                "description": "测试群",
                "chat_rules": {"tone": "轻松"},
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    ctx = ContextManager(tmp_path / "test.db")
    bootstrap_rules_if_empty(ctx, style_dir)

    repo = RuleRepository(ctx)
    assert repo.get_active_rule("global", "__global__") is not None
    assert repo.get_active_rule("group", "group_demo") is not None
