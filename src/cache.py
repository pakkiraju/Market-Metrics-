"""In-memory TTL cache for non-real-time data."""

import json
import time
import threading
from pathlib import Path

# TTL in seconds: 0 = no cache
FAST = 300       # 5 min
MEDIUM = 3600    # 1 hour
SLOW = 7200      # 2 hours

# Key Metrics: 1 hour (not real-time)
KEY_METRICS_TTL = 3600

# Keys that persist to disk (survive server restarts)
_DISK_PERSISTENT_KEYS = frozenset({
    "all_key_metrics",
    "qulla_episodic_v2",
    "qulla_parabolic_v2",
    "qulla_breakouts_v2",
    "minervini_table",
    "oneil_table",
    "sector_data",
    "97_club",
    "9m_movers",
})

# Key prefixes that persist to disk (e.g. watchlist_quotes_AAPL,MSFT)
_DISK_PERSISTENT_PREFIXES = frozenset({"watchlist_quotes_"})

_store: dict[str, tuple[object, float]] = {}
_lock = threading.Lock()
_CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"


def _should_persist(key: str) -> bool:
    """True if key should be persisted to disk."""
    if key in _DISK_PERSISTENT_KEYS:
        return True
    return any(key.startswith(p) for p in _DISK_PERSISTENT_PREFIXES)


def _disk_path(key: str) -> Path:
    return _CACHE_DIR / f"{key}.json"


def _load_from_disk(key: str) -> tuple[object, float] | None:
    """Load value from disk if present and not expired. Returns (value, monotonic_expiry) or None."""
    if not _should_persist(key):
        return None
    path = _disk_path(key)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        expiry = data.get("_expiry")
        if expiry is not None and time.time() >= expiry:
            path.unlink(missing_ok=True)
            return None
        value = data.get("value")
        if value is None:
            return None
        # Convert absolute expiry to monotonic for in-memory store
        if expiry is None:
            monotonic_expiry = float("inf")
        else:
            remaining = max(0, expiry - time.time())
            monotonic_expiry = time.monotonic() + remaining
        return (value, monotonic_expiry)
    except (json.JSONDecodeError, OSError, KeyError):
        return None


def _save_to_disk(key: str, value: object, expiry: float):
    """Persist value to disk."""
    if not _should_persist(key):
        return
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _disk_path(key)
    try:
        payload = {"value": value, "_expiry": expiry if expiry != float("inf") else None}
        path.write_text(json.dumps(payload, default=str))
    except (TypeError, OSError):
        pass


def get(key: str):
    """Return cached value if present and not expired, else None."""
    with _lock:
        entry = _store.get(key)
        if entry is not None:
            value, expiry = entry
            if expiry > 0 and time.monotonic() >= expiry:
                del _store[key]
            else:
                return value
        # Memory miss: try disk for persistent keys
        disk_result = _load_from_disk(key)
        if disk_result is not None:
            disk_val, monotonic_expiry = disk_result
            _store[key] = (disk_val, monotonic_expiry)
            return disk_val
        return None


def put(key: str, value, ttl: int = 0):
    """Store value with optional TTL in seconds. ttl=0 means no expiry."""
    with _lock:
        expiry = time.monotonic() + ttl if ttl > 0 else float("inf")
        _store[key] = (value, expiry)
        if _should_persist(key):
            disk_expiry = time.time() + ttl if ttl > 0 else time.time() + 86400 * 365  # 1 year if no TTL
            _save_to_disk(key, value, disk_expiry)


def invalidate(key: str | None = None):
    """Remove key from cache, or clear all if key is None."""
    with _lock:
        if key is None:
            _store.clear()
            for k in _DISK_PERSISTENT_KEYS:
                _disk_path(k).unlink(missing_ok=True)
            # Remove disk files for prefix-matched keys (e.g. watchlist_quotes_*)
            if _CACHE_DIR.exists():
                for p in _CACHE_DIR.iterdir():
                    if p.suffix == ".json" and any(p.stem.startswith(prefix) for prefix in _DISK_PERSISTENT_PREFIXES):
                        p.unlink(missing_ok=True)
        elif key in _store:
            del _store[key]
            if _should_persist(key):
                _disk_path(key).unlink(missing_ok=True)
