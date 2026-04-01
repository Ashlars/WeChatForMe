from __future__ import annotations

import uuid
from datetime import datetime

from loguru import logger

from src.backend.base import IncomingMessage, MessageCallback, WeChatBackend
from src.backend.macos.automator import UIAutomator
from src.backend.macos.message_monitor import MessageMonitor


class MacOSBackend(WeChatBackend):
    def __init__(self, app_name: str = "微信") -> None:
        self._automator = UIAutomator()
        self._monitor = MessageMonitor()
        self._message_callback: MessageCallback | None = None

        self._monitor.on_notification(self._on_new_message)

    def start(self) -> None:
        self._monitor.start()
        logger.info("MacOSBackend started")

    def stop(self) -> None:
        self._monitor.stop()
        logger.info("MacOSBackend stopped")

    def send_message(self, target_name: str, message: str) -> bool:
        return self._automator.send_message(target_name, message)

    def on_new_message(self, callback: MessageCallback) -> None:
        self._message_callback = callback

    def _on_new_message(self, parsed: dict) -> None:
        if not self._message_callback:
            return

        msg = IncomingMessage(
            sender_name=str(parsed["sender_name"]),
            sender_id=str(parsed["sender_id"]),
            content=parsed["content"],
            is_group=parsed["is_group"],
            group_name=parsed.get("group_name"),
            group_id=parsed.get("group_id"),
            msg_id=parsed.get("msg_id", f"db_{uuid.uuid4().hex[:12]}"),
            timestamp=datetime.fromtimestamp(parsed["timestamp"])
            if isinstance(parsed.get("timestamp"), (int, float))
            else datetime.now(),
        )
        self._message_callback(msg)
