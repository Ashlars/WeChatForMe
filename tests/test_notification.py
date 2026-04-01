from unittest.mock import MagicMock
from src.backend.macos.notification import NotificationMonitor


def test_parse_notification_private():
    monitor = NotificationMonitor(app_name="微信")
    result = monitor._parse_notification(
        title="张三",
        subtitle=None,
        body="你好啊，最近怎么样",
    )
    assert result is not None
    assert result["sender_name"] == "张三"
    assert result["content"] == "你好啊，最近怎么样"
    assert result["is_group"] is False


def test_parse_notification_group():
    monitor = NotificationMonitor(app_name="微信")
    result = monitor._parse_notification(
        title="工作群",
        subtitle="李四",
        body="明天开会吗",
    )
    assert result is not None
    assert result["sender_name"] == "李四"
    assert result["group_name"] == "工作群"
    assert result["is_group"] is True


def test_callback_registration():
    monitor = NotificationMonitor(app_name="微信")
    cb = MagicMock()
    monitor.on_notification(cb)
    assert monitor._callback is cb


def test_parse_notification_empty():
    monitor = NotificationMonitor(app_name="微信")
    result = monitor._parse_notification(title=None, subtitle=None, body=None)
    assert result is None
