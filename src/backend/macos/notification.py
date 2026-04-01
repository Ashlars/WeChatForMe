from __future__ import annotations

from typing import Callable

from loguru import logger

try:
    import objc
    from Foundation import NSDistributedNotificationCenter
    HAS_PYOBJC = True
except ImportError:
    HAS_PYOBJC = False


class NotificationMonitor:
    def __init__(self, app_name: str = "微信") -> None:
        self._app_name = app_name
        self._callback: Callable | None = None
        self._running = False

    def on_notification(self, callback: Callable) -> None:
        self._callback = callback

    def _parse_notification(
        self, title: str | None, subtitle: str | None, body: str | None
    ) -> dict | None:
        if not title and not body:
            return None

        if subtitle:
            return {
                "sender_name": subtitle,
                "group_name": title,
                "content": body or "",
                "is_group": True,
            }
        else:
            return {
                "sender_name": title or "",
                "group_name": None,
                "content": body or "",
                "is_group": False,
            }

    def start(self) -> None:
        if not HAS_PYOBJC:
            logger.error("pyobjc not available — notification monitoring disabled")
            return
        self._running = True
        logger.info("NotificationMonitor started for {}", self._app_name)
        center = NSDistributedNotificationCenter.defaultCenter()
        center.addObserver_selector_name_object_(
            self, objc.selector(self._handle_notification_, signature=b"v@:@"),
            None, None,
        )

    def _handle_notification_(self, notification) -> None:
        if not self._running or not self._callback:
            return
        try:
            user_info = notification.userInfo()
            if not user_info:
                return
            app = user_info.get("app") or user_info.get("bundleID") or ""
            if "wechat" not in str(app).lower() and "xinwei" not in str(app).lower():
                return

            title = user_info.get("title")
            subtitle = user_info.get("subtitle")
            body = user_info.get("body") or user_info.get("message")

            parsed = self._parse_notification(title, subtitle, body)
            if parsed:
                logger.debug("WeChat notification: {}", parsed)
                self._callback(parsed)
        except Exception as e:
            logger.error("Error handling notification: {}", e)

    def stop(self) -> None:
        self._running = False
        logger.info("NotificationMonitor stopped")
