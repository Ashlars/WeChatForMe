from unittest.mock import patch
from src.backend.macos.automator import UIAutomator


@patch("src.backend.macos.automator.UIAutomator._run_applescript")
def test_activate_wechat(mock_run):
    mock_run.return_value = (True, "")
    auto = UIAutomator()
    assert auto._activate_wechat() is True
    script = mock_run.call_args[0][0]
    assert "WeChat" in script
    assert "frontmost" in script


@patch("src.backend.macos.automator.UIAutomator._run_applescript")
def test_search_and_select(mock_run):
    mock_run.return_value = (True, "")
    auto = UIAutomator()
    assert auto._search_and_select("张三") is True
    script = mock_run.call_args[0][0]
    assert "张三" in script


@patch("src.backend.macos.automator.UIAutomator._run_applescript")
@patch("src.backend.macos.automator.UIAutomator._get_window_geometry")
def test_click_input_and_type(mock_geo, mock_run):
    mock_geo.return_value = (0, 0, 1000, 800)
    mock_run.return_value = (True, "")
    auto = UIAutomator()
    assert auto._click_input_and_type("你好") is True
    script = mock_run.call_args[0][0]
    assert "你好" in script


@patch("src.backend.macos.automator.UIAutomator._run_applescript")
@patch("src.backend.macos.automator.UIAutomator._get_window_geometry")
def test_send_message_calls_sequence(mock_geo, mock_run):
    mock_geo.return_value = (0, 0, 1000, 800)
    mock_run.return_value = (True, "")
    auto = UIAutomator()
    result = auto.send_message("张三", "你好")
    assert result is True
    assert mock_run.call_count >= 3
