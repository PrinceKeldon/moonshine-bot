"""Load and validate configuration."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from loguru import logger


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config.yaml"


def load_config(path: Path | str = DEFAULT_CONFIG) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    logger.info(f"Loaded config from {path}")
    return cfg


def load_blacklist(path: Path | str) -> set[str]:
    path = Path(path)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[]", encoding="utf-8")
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return set(str(x).lower() for x in data)
    except Exception as e:
        logger.warning(f"Failed to load blacklist {path}: {e}")
        return set()


def save_blacklist(path: Path | str, items: set[str]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(items), indent=2), encoding="utf-8")
    logger.debug(f"Saved blacklist ({len(items)} items) → {path}")
