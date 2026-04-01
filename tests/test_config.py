import yaml
from src.core.config import ConfigManager


def test_load_config(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump({
        "wechat": {"backend": "macos"},
        "claude": {"chat_model": "claude-sonnet-4-6", "api_key_env": "ANTHROPIC_API_KEY"},
        "reply_rules": {"private_chat": {"enabled": True, "delay_range": [2, 8]}},
        "security": {"rate_limit": 30, "pause_keyword": "#人工"},
    }))
    cm = ConfigManager(config_file)
    assert cm.get("wechat.backend") == "macos"
    assert cm.get("claude.chat_model") == "claude-sonnet-4-6"
    assert cm.get("reply_rules.private_chat.enabled") is True
    assert cm.get("security.rate_limit") == 30


def test_get_nested_default(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump({"wechat": {"backend": "macos"}}))
    cm = ConfigManager(config_file)
    assert cm.get("nonexistent.key", "default") == "default"


def test_reload_on_change(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump({"wechat": {"backend": "macos"}}))
    cm = ConfigManager(config_file)
    assert cm.get("wechat.backend") == "macos"
    config_file.write_text(yaml.dump({"wechat": {"backend": "wechatferry"}}))
    cm.reload()
    assert cm.get("wechat.backend") == "wechatferry"
