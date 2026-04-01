import yaml
from src.core.style import StyleManager


def test_load_default_style(tmp_path):
    style_dir = tmp_path / "styles"
    style_dir.mkdir()
    (style_dir / "default.yaml").write_text(yaml.dump({
        "chat_rules": {
            "tone": "随意",
            "reply_length": "短",
            "forbidden_patterns": ["作为AI"],
        }
    }))
    sm = StyleManager(style_dir)
    rules = sm.get_chat_rules()
    assert rules["tone"] == "随意"
    assert "作为AI" in rules["forbidden_patterns"]


def test_contact_style_override(tmp_path):
    style_dir = tmp_path / "styles"
    style_dir.mkdir()
    (style_dir / "default.yaml").write_text(yaml.dump({
        "chat_rules": {"tone": "随意", "reply_length": "短"}
    }))
    contacts_dir = style_dir / "contacts"
    contacts_dir.mkdir()
    (contacts_dir / "wxid_abc.yaml").write_text(yaml.dump({
        "wxid": "wxid_abc",
        "chat_rules": {"tone": "正式"}
    }))
    sm = StyleManager(style_dir)
    rules = sm.get_chat_rules(contact_id="wxid_abc")
    assert rules["tone"] == "正式"
    assert rules["reply_length"] == "短"


def test_group_style(tmp_path):
    style_dir = tmp_path / "styles"
    style_dir.mkdir()
    (style_dir / "default.yaml").write_text(yaml.dump({
        "chat_rules": {"tone": "随意"}
    }))
    groups_dir = style_dir / "groups"
    groups_dir.mkdir()
    (groups_dir / "测试群.yaml").write_text(yaml.dump({
        "group_id": "123@chatroom",
        "description": "测试群聊",
        "chat_rules": {"tone": "轻松", "role": "群员"}
    }))
    sm = StyleManager(style_dir)
    rules = sm.get_chat_rules(group_id="123@chatroom")
    assert rules["tone"] == "轻松"
    assert rules["role"] == "群员"


def test_format_style_prompt(tmp_path):
    style_dir = tmp_path / "styles"
    style_dir.mkdir()
    (style_dir / "default.yaml").write_text(yaml.dump({
        "chat_rules": {"tone": "随意", "forbidden_patterns": ["作为AI"]}
    }))
    sm = StyleManager(style_dir)
    prompt = sm.format_style_prompt()
    assert "随意" in prompt
    assert "作为AI" in prompt


def test_get_forbidden_patterns(tmp_path):
    style_dir = tmp_path / "styles"
    style_dir.mkdir()
    (style_dir / "default.yaml").write_text(yaml.dump({
        "chat_rules": {"forbidden_patterns": ["作为AI", "我来为你"]}
    }))
    sm = StyleManager(style_dir)
    patterns = sm.get_forbidden_patterns()
    assert "作为AI" in patterns
    assert "我来为你" in patterns


def test_backward_compat_get_style(tmp_path):
    style_dir = tmp_path / "styles"
    style_dir.mkdir()
    (style_dir / "default.yaml").write_text(yaml.dump({
        "chat_rules": {"tone": "随意"}
    }))
    sm = StyleManager(style_dir)
    style = sm.get_style()
    assert style["tone"] == "随意"
