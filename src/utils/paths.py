"""Repository-relative path helpers, resolved from config/settings.yaml."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def load_settings() -> dict:
    settings_path = PROJECT_ROOT / "config" / "settings.yaml"
    with settings_path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def raw_dir() -> Path:
    path = PROJECT_ROOT / load_settings()["paths"]["raw_dir"]
    path.mkdir(parents=True, exist_ok=True)
    return path


def processed_dir() -> Path:
    path = PROJECT_ROOT / load_settings()["paths"]["processed_dir"]
    path.mkdir(parents=True, exist_ok=True)
    return path


def results_dir(use_case: str) -> Path:
    path = PROJECT_ROOT / load_settings()["paths"]["results_dir"] / use_case
    path.mkdir(parents=True, exist_ok=True)
    return path
