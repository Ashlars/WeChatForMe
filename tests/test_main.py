from unittest.mock import patch, MagicMock
from src.main import create_app


@patch("src.main.MacOSBackend")
@patch("src.main.ContextManager")
@patch("src.main.ConfigManager")
def test_create_app(mock_config, mock_ctx, mock_backend):
    mock_config.return_value.get.side_effect = lambda key, default=None: {
        "wechat.backend": "macos",
        "wechat.macos.notification_app": "微信",
        "claude.chat_model": "claude-sonnet-4-6",
        "claude.supervisor_model": "claude-opus-4-6",
        "claude.api_key_env": "ANTHROPIC_API_KEY",
        "reply_rules.private_chat.whitelist_only": True,
        "reply_rules.private_chat.max_reply_length": 200,
        "reply_rules.private_chat.delay_range": [2, 8],
        "security.rate_limit": 30,
        "security.sensitive_words": [],
        "security.pause_keyword": "#人工",
        "security.min_delay": 1,
        "scheduler.supervisor_interval": "0 */6 * * *",
        "scheduler.proactive_tasks": [],
        "user.name": "小明",
    }.get(key, default)
    mock_config.return_value.data = {}

    app = create_app(
        config_path="/tmp/config.yaml",
        style_dir="/tmp/styles",
        db_path="/tmp/test.db",
    )
    assert app is not None
