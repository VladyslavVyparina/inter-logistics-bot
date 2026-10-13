from __future__ import annotations

import json
import logging
import secrets
import string
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

from config import LISTINGS_PATH

log = logging.getLogger(__name__)

KYIV_TZ = ZoneInfo("Europe/Kyiv")
KEEP_DAYS = 30
_ALPHABET = string.ascii_lowercase + string.digits


def _path() -> Path:
    return Path(LISTINGS_PATH)


def _load() -> dict[str, Any]:
    path = _path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log.error("Не вдалося прочитати listings: %s", e)
        return {}


def _save(data: dict[str, Any]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _prune(data: dict[str, Any]) -> dict[str, Any]:
    cutoff = datetime.now(KYIV_TZ) - timedelta(days=KEEP_DAYS)
    kept: dict[str, Any] = {}
    for key, item in data.items():
        created = str(item.get("created_at") or "")
        try:
            dt = datetime.strptime(created, "%Y-%m-%d %H:%M:%S").replace(tzinfo=KYIV_TZ)
        except ValueError:
            kept[key] = item
            continue
        if dt >= cutoff:
            kept[key] = item
    return kept


def new_listing_id() -> str:
    data = _load()
    for _ in range(20):
        listing_id = "".join(secrets.choice(_ALPHABET) for _ in range(8))
        if listing_id not in data:
            return listing_id
    return secrets.token_hex(4)


def save_listing(listing: dict[str, Any]) -> str:
    listing_id = listing.get("id") or new_listing_id()
    listing["id"] = listing_id
    listing.setdefault("created_at", datetime.now(KYIV_TZ).strftime("%Y-%m-%d %H:%M:%S"))
    data = _prune(_load())
    data[listing_id] = listing
    _save(data)
    return listing_id


def get_listing(listing_id: str) -> Optional[dict[str, Any]]:
    if not listing_id:
        return None
    return _load().get(listing_id)
