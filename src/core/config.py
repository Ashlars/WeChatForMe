from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from loguru import logger


class ConfigManager:
    def __init__(self, config_path: Path) -> None:
        self._path = Path(config_path)
        self._data: dict = {}
        self.reload()

    def reload(self) -> None:
        with open(self._path) as f:
            self._data = yaml.safe_load(f) or {}
        logger.debug("Config loaded from {}", self._path)

    def get(self, dotted_key: str, default: Any = None) -> Any:
        keys = dotted_key.split(".")
        node = self._data
        for k in keys:
            if isinstance(node, dict) and k in node:
                node = node[k]
            else:
                return default
        return node

    @property
    def data(self) -> dict:
        return self._data
