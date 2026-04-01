from __future__ import annotations

import random
import time
from collections import defaultdict

from loguru import logger


class SecurityManager:
    def __init__(
        self,
        sensitive_words: list[str],
        rate_limit: int,
        pause_keyword: str,
    ) -> None:
        self._sensitive_words = sensitive_words
        self._rate_limit = rate_limit
        self._pause_keyword = pause_keyword
        self._reply_counts: dict[str, list[float]] = defaultdict(list)

    def contains_sensitive(self, text: str) -> bool:
        return any(w in text for w in self._sensitive_words)

    def is_pause_command(self, text: str) -> bool:
        return self._pause_keyword in text

    def check_rate_limit(self, contact_id: str) -> bool:
        now = time.time()
        hour_ago = now - 3600
        self._reply_counts[contact_id] = [
            t for t in self._reply_counts[contact_id] if t > hour_ago
        ]
        return len(self._reply_counts[contact_id]) < self._rate_limit

    def record_reply(self, contact_id: str) -> None:
        self._reply_counts[contact_id].append(time.time())

    def generate_delay(self, min_sec: float, max_sec: float) -> float:
        return random.uniform(min_sec, max_sec)
