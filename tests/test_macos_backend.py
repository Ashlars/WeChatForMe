from unittest.mock import patch, MagicMock
from src.backend.macos.backend import MacOSBackend
from src.backend.base import WeChatBackend


def test_implements_abstract_interface():
    assert issubclass(MacOSBackend, WeChatBackend)


@patch("src.backend.macos.backend.UIAutomator")
@patch("src.backend.macos.backend.MessageMonitor")
def test_send_message_delegates_to_automator(mock_monitor, mock_auto):
    instance = mock_auto.return_value
    instance.send_message.return_value = True

    backend = MacOSBackend()
    result = backend.send_message("张三", "你好")
    assert result is True
    instance.send_message.assert_called_once_with("张三", "你好")


@patch("src.backend.macos.backend.UIAutomator")
@patch("src.backend.macos.backend.MessageMonitor")
def test_on_new_message_registers_callback(mock_monitor, mock_auto):
    backend = MacOSBackend()
    cb = MagicMock()
    backend.on_new_message(cb)
    assert backend._message_callback is cb
