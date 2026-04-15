from __future__ import annotations

import subprocess
import threading
import time

from loguru import logger


class UIAutomator:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._verified_targets: set[str] = set()

    # ── low-level helpers ──────────────────────────────────────

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
        from Quartz import (
            CGEventCreateMouseEvent,
            CGEventPost,
            kCGEventLeftMouseDown,
            kCGEventLeftMouseUp,
            kCGHIDEventTap,
        )
        event_down = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, (x, y), 0)
        event_up = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, (x, y), 0)
        CGEventPost(kCGHIDEventTap, event_down)
        CGEventPost(kCGHIDEventTap, event_up)

    def _escape(self) -> None:
        self._run_applescript('''
            tell application "System Events"
                tell process "WeChat"
                    key code 53
                end tell
            end tell
        ''')

    # ── atomic steps ───────────────────────────────────────────

    def _step_activate(self) -> bool:
        """Step 1: Bring WeChat to front and verify it's frontmost."""
        ok, _ = self._run_applescript('''
            tell application "System Events"
                set frontmost of process "WeChat" to true
            end tell
        ''')
        if not ok:
            logger.error("[STEP 1] Failed to activate WeChat")
            return False

        time.sleep(0.5)

        # Verify WeChat is actually frontmost
        ok, out = self._run_applescript('''
            tell application "System Events"
                return name of first process whose frontmost is true
            end tell
        ''')
        if not ok or "WeChat" not in out:
            logger.error("[STEP 1] WeChat is not frontmost (got: {})", out)
            return False

        logger.debug("[STEP 1] WeChat activated OK")
        return True

    def _step_search(self, target_name: str) -> bool:
        """Step 2: Open search, clear, paste target name."""
        escaped = target_name.replace("\\", "\\\\").replace('"', '\\"')

        # Open search
        ok, _ = self._run_applescript('''
            tell application "System Events"
                tell process "WeChat"
                    keystroke "f" using command down
                end tell
            end tell
        ''')
        if not ok:
            logger.error("[STEP 2] Failed to open search")
            return False
        time.sleep(0.5)

        # Clear and paste
        ok, _ = self._run_applescript(f'''
            set the clipboard to "{escaped}"
            tell application "System Events"
                tell process "WeChat"
                    keystroke "a" using command down
                    delay 0.1
                    key code 51
                    delay 0.3
                    keystroke "v" using command down
                end tell
            end tell
        ''')
        if not ok:
            logger.error("[STEP 2] Failed to paste search text")
            return False

        # Wait for search results
        time.sleep(2.5)
        logger.debug("[STEP 2] Search pasted OK: {}", target_name)
        return True

    def _step_select(self) -> bool:
        """Step 3: Select the first search result."""
        ok, _ = self._run_applescript('''
            tell application "System Events"
                tell process "WeChat"
                    keystroke return
                end tell
            end tell
        ''')
        if not ok:
            logger.error("[STEP 3] Failed to select search result")
            return False

        time.sleep(1.0)
        logger.debug("[STEP 3] Search result selected OK")
        return True

    def _step_confirm_target(self, target_name: str) -> bool:
        """Step 4: First-time target confirmation via dialog."""
        if target_name in self._verified_targets:
            return True

        logger.info("[STEP 4] First send to '{}', asking user to confirm...", target_name)
        escaped = target_name.replace("\\", "\\\\").replace('"', '\\"')
        ok, output = self._run_applescript(f'''
            display dialog "请确认微信当前打开的是「{escaped}」的聊天窗口？\\n\\n确认后，以后发给「{escaped}」的消息将不再询问。" buttons {{"取消", "确认正确"}} default button "确认正确" with title "替我聊 - 首次发送确认" giving up after 30
            if button returned of result is "确认正确" then
                return "confirmed"
            else
                return "cancelled"
            end if
        ''', timeout=35)

        if ok and "confirmed" in output:
            self._verified_targets.add(target_name)
            logger.info("[STEP 4] User confirmed target '{}'", target_name)
            return True

        logger.warning("[STEP 4] User rejected target '{}'", target_name)
        return False

    def _step_paste_message(self, message: str) -> bool:
        """Step 5: Click input area and paste message."""
        geo = self._get_window_geometry()
        if not geo:
            logger.error("[STEP 5] Cannot get WeChat window geometry")
            return False

        wx, wy, ww, wh = geo
        input_x = wx + int(ww * 0.65)
        input_y = wy + wh - 60
        self._click(input_x, input_y)
        time.sleep(0.3)

        # Verify click landed (check if WeChat is still front)
        ok, out = self._run_applescript('''
            tell application "System Events"
                return name of first process whose frontmost is true
            end tell
        ''')
        if not ok or "WeChat" not in out:
            logger.error("[STEP 5] WeChat lost focus after click")
            return False

        escaped = message.replace("\\", "\\\\").replace('"', '\\"')
        ok, _ = self._run_applescript(f'''
            set the clipboard to "{escaped}"
            tell application "System Events"
                tell process "WeChat"
                    keystroke "v" using command down
                end tell
            end tell
        ''')
        if not ok:
            logger.error("[STEP 5] Failed to paste message")
            return False

        time.sleep(0.3)
        logger.debug("[STEP 5] Message pasted OK ({} chars)", len(message))
        return True

    def _step_send(self) -> bool:
        """Step 6: Press Enter to send."""
        ok, _ = self._run_applescript('''
            tell application "System Events"
                tell process "WeChat"
                    keystroke return
                end tell
            end tell
        ''')
        if not ok:
            logger.error("[STEP 6] Failed to press Enter")
            return False

        logger.debug("[STEP 6] Enter pressed OK")
        return True

    def _get_window_geometry(self) -> tuple[int, int, int, int] | None:
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

    # ── main entry point ──────────────────────────────────────

    def send_message(self, target_name: str, message: str, retries: int = 2) -> bool:
        """Send a message through WeChat UI automation.

        Pipeline: activate → search → select → confirm → paste → send
        Each step is atomic. If any step fails, abort and retry from scratch.
        """
        with self._lock:
            last_failed_step = ""

            for attempt in range(retries + 1):
                if attempt > 0:
                    logger.info(
                        "Retry {}/{} for '{}' (last failure: {})",
                        attempt, retries, target_name, last_failed_step,
                    )
                    self._escape()
                    time.sleep(1.5)

                # Step 1: Activate
                if not self._step_activate():
                    last_failed_step = "activate"
                    continue

                # Step 2: Search
                if not self._step_search(target_name):
                    last_failed_step = "search"
                    self._escape()
                    continue

                # Step 3: Select
                if not self._step_select():
                    last_failed_step = "select"
                    self._escape()
                    continue

                # Step 4: Confirm (first time only)
                if not self._step_confirm_target(target_name):
                    last_failed_step = "confirm_rejected"
                    self._escape()
                    return False  # User rejected — don't retry

                # Step 5: Paste
                if not self._step_paste_message(message):
                    last_failed_step = "paste"
                    self._escape()
                    continue

                # Step 6: Send
                if not self._step_send():
                    last_failed_step = "send"
                    continue

                logger.info("Message sent to '{}' (attempt {})", target_name, attempt + 1)
                return True

            logger.error(
                "FAILED to send to '{}' after {} attempts (last: {})",
                target_name, retries + 1, last_failed_step,
            )
            return False
