from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable


@dataclass
class IncomingMessage:
    sender_name: str
    sender_id: str
    content: str
    is_group: bool
    group_id: str | None = None
    group_name: str | None = None
    msg_id: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)


MessageCallback = Callable[[IncomingMessage], None]


class WeChatBackend(ABC):
    @abstractmethod
    def start(self) -> None:
        """Start listening for messages."""

    @abstractmethod
    def stop(self) -> None:
        """Stop listening."""

    @abstractmethod
    def send_message(self, target_name: str, message: str) -> bool:
        """Send a text message to a contact or group by name. Returns success."""

    @abstractmethod
    def on_new_message(self, callback: MessageCallback) -> None:
        """Register a callback for incoming messages."""
