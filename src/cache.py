"""Two-layer cache: in-memory + disk (pickle) with per-key TTL.

TTL tiers (shorter with Elite API for fresher data):
  FAST   =  2 min  (daily movers, 97 club, 9M movers, 20% weekly)
  MEDIUM = 10 min  (key metrics, sector SPDRs, composite indicators)
  SLOW   = 30 min  (stage analysis, leading industries)

When market is closed all tiers extend to 12 hours.
"""

import hashlib
import logging
import pickle
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

_mem: dict = {}

CACHE_DIR = Path(__file__).resolve().parent.parent / "config" / ".cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

ET = timezone(timedelta(hours=-5))

FAST = 120        # 2 min
MEDIUM = 600      # 10 min
SLOW = 1800       # 30 min
CLOSED = 43200    # 12 hours


def _is_market_open() -> bool:
    now = datetime.now(ET)
    if now.weekday() >= 5:
        return False
    t = now.hour * 60 + now.minute
    return 9 * 60 + 30 <= t < 16 * 60


def _effective_ttl(ttl: int) -> int:
    if _is_market_open():
        return ttl
    return max(ttl, CLOSED)


def _disk_path(key: str) -> Path:
    safe = hashlib.md5(key.encode()).hexdigest()
    return CACHE_DIR / f"{safe}.pkl"


def get(key: str):
    """Return cached value or None if expired / missing."""
    entry = _mem.get(key)
    if entry is not None:
        value, ts, ttl = entry
        if time.time() - ts <= _effective_ttl(ttl):
            return value
        del _mem[key]

    dp = _disk_path(key)
    if dp.exists():
        try:
            with open(dp, "rb") as f:
                value, ts, ttl = pickle.load(f)
            if time.time() - ts <= _effective_ttl(ttl):
                _mem[key] = (value, ts, ttl)
                return value
            dp.unlink(missing_ok=True)
        except Exception:
            dp.unlink(missing_ok=True)

    return None


def put(key: str, value, ttl: int = MEDIUM):
    """Store value in both memory and disk."""
    ts = time.time()
    _mem[key] = (value, ts, ttl)
    dp = _disk_path(key)
    try:
        with open(dp, "wb") as f:
            pickle.dump((value, ts, ttl), f, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception as e:
        logger.warning("Disk cache write failed for %s: %s", key, e)


def invalidate(key: str | None = None):
    """Clear one key or everything."""
    if key is None:
        _mem.clear()
        for p in CACHE_DIR.glob("*.pkl"):
            p.unlink(missing_ok=True)
    else:
        _mem.pop(key, None)
        _disk_path(key).unlink(missing_ok=True)
