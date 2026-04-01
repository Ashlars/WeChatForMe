from __future__ import annotations

import subprocess
import threading
import time

from loguru import logger


class UIAutomator:
    def __init__(self) -> None:
        self._lock = threading.Lock()

    def _run_applescript(self, script: str, timeout: int = 15) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=timeout,
            )
            success = result.returncode == 0
            output = result.stdout.strip() or result.stderr.strip()
            if not success:
                logger.warning("AppleScript failed: {}", output)
            return success, output
        except subprocess.TimeoutExpired:
            logger.error("AppleScript timed out")
            return False, "timeout"

    def _click(self, x: float, y: float) -> None:
        """Click at screen coordinates using Quartz CGEvent."""
        from Quartz import (
            CGEventCreateMouseEvent,
            CGEventPost,
            kCGEventLeftMouseDown,
            kCGEventLeftMouseUp,
            kCGHIDEventTap,
        )

        event_down = CGEventCreateMouseEvent(
            None, kCGEventLeftMouseDown, (x, y), 0
        )
        event_up = CGEventCreateMouseEvent(
            None, kCGEventLeftMouseUp, (x, y), 0
        )
        CGEventPost(kCGHIDEventTap, event_down)
        CGEventPost(kCGHIDEventTap, event_up)

    def _get_window_geometry(self) -> tuple[int, int, int, int] | None:
        """Return (x, y, width, height) of WeChat window 1."""
        ok, out = self._run_applescript('''
            tell application "System Events"
                tell process "WeChat"
                    set winPos to position of window 1
                    set winSize to size of window 1
                    return (item 1 of winPos as text) & "," & (item 2 of winPos as text) & "," & (item 1 of winSize as text) & "," & (item 2 of winSize as text)
                end tell
            end tell
        ''')
        if not ok:
            return None
        parts = out.split(",")
        return int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])

    def _activate_wechat(self) -> bool:
        ok, _ = self._run_applescript('''
            tell application "System Events"
                set frontmost of process "WeChat" to true
            end tell
        ''')
        return ok

    def _search_and_select(self, target_name: str) -> bool:
        """Open search, paste contact name via clipboard, select first result."""
        escaped = target_name.replace("\\", "\\\\").replace('"', '\\"')
        ok, _ = self._run_applescript(f'''
            set the clipboard to "{escaped}"
            tell application "System Events"
                tell process "WeChat"
                    keystroke "f" using command down
                    delay 0.8
                    keystroke "v" using command down
                    delay 2
                    keystroke return
                    delay 0.8
                end tell
            end tell
        ''')
        return ok

    def _click_input_and_type(self, message: str) -> bool:
        """Click the message input area and paste the message."""
        geo = self._get_window_geometry()
        if not geo:
            logger.warning("Cannot get WeChat window geometry")
            return False

        wx, wy, ww, wh = geo
        # Input box is at the bottom-center of the right panel.
        # Left panel is ~30% of width; input box center is in the right 70%.
        input_x = wx + int(ww * 0.65)
        input_y = wy + wh - 60
        self._click(input_x, input_y)
        time.sleep(0.3)

        escaped = message.replace("\\", "\\\\").replace('"', '\\"')
        ok, _ = self._run_applescript(f'''
            set the clipboard to "{escaped}"
            tell application "System Events"
                tell process "WeChat"
                    keystroke "v" using command down
                end tell
            end tell
        ''')
        return ok

    def _send_enter(self) -> bool:
        ok, _ = self._run_applescript('''
            tell application "System Events"
                tell process "WeChat"
                    keystroke return
                end tell
            end tell
        ''')
        return ok

    def _escape(self) -> bool:
        ok, _ = self._run_applescript('''
            tell application "System Events"
                tell process "WeChat"
                    key code 53
                end tell
            end tell
        ''')
        return ok

    def send_message(self, target_name: str, message: str, retries: int = 2) -> bool:
        with self._lock:
            for attempt in range(retries + 1):
                if attempt > 0:
                    logger.info("Retry attempt {} for {}", attempt, target_name)
                    time.sleep(1)

                if not self._activate_wechat():
                    continue
                time.sleep(0.5)

                if not self._search_and_select(target_name):
                    self._escape()
                    continue
                time.sleep(0.5)

                if not self._click_input_and_type(message):
                    continue
                time.sleep(0.3)

                if self._send_enter():
                    logger.info("Message sent to {}", target_name)
                    return True

            logger.error(
                "Failed to send message to {} after {} attempts",
                target_name, retries + 1,
            )
            return False
