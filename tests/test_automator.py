from unittest.mock import patch, MagicMock
from src.backend.macos.automator import UIAutomator


@patch("src.backend.macos.automator.UIAutomator._run_applescript")
def test_step_activate(mock_run):
    mock_run.return_value = (True, "WeChat")
    auto = UIAutomator()
    assert auto._step_activate() is True


@patch("src.backend.macos.automator.UIAutomator._run_applescript")
def test_step_search(mock_run):
    mock_run.return_value = (True, "")
    auto = UIAutomator()
    assert auto._step_search("张三") is True


@patch("src.backend.macos.automator.UIAutomator._run_applescript")
@patch("src.backend.macos.automator.UIAutomator._get_window_geometry")
def test_step_paste_message(mock_geo, mock_run):
    mock_geo.return_value = (0, 0, 1000, 800)
    mock_run.return_value = (True, "WeChat")
    auto = UIAutomator()
    assert auto._step_paste_message("你好") is True


@patch("src.backend.macos.automator.UIAutomator._run_applescript")
@patch("src.backend.macos.automator.UIAutomator._get_window_geometry")
def test_send_message_calls_sequence(mock_geo, mock_run):
    mock_geo.return_value = (0, 0, 1000, 800)
    mock_run.return_value = (True, "WeChat")
    auto = UIAutomator()
    # Pre-verify target to skip confirmation dialog
    auto._verified_targets.add("张三")
    result = auto.send_message("张三", "你好")
    assert result is True
    assert mock_run.call_count >= 4
