from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from flask import current_app


@lru_cache(maxsize=4)
def _load_path(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("categories.yaml must be a mapping")
    return data


def reload_categories() -> None:
    _load_path.cache_clear()


def get_vocabulary() -> dict[str, Any]:
    path = current_app.config["CATEGORIES_PATH"]
    if not Path(path).is_file():
        raise FileNotFoundError(f"categories file not found: {path}")
    return _load_path(path)
