"""
core/cache.py — Simple in-process TTL cache for lightweight metrics.

No Redis dependency for caching — uses a plain dict with timestamps.
For high-traffic production you can swap to Redis-backed caching (Phase 5+)
without changing call sites.

Usage:
    from app.core.cache import ttl_cache

    @ttl_cache(ttl_seconds=20)
    def expensive_query(org_id: str) -> dict:
        ...
"""

import time
import threading
from functools import wraps
from typing import Any, Callable


_cache: dict[str, tuple[float, Any]] = {}
_lock = threading.Lock()


def ttl_cache(ttl_seconds: int = 20):
    """
    Decorator that caches the return value of a function for `ttl_seconds`.
    Cache key is built from the function name + positional + keyword args.
    Thread-safe via a module-level lock.

    Exception safety:
        If the decorated function raises an exception, the exception propagates
        normally and NO cache entry is written. This prevents a transient error
        (e.g. DB temporarily unavailable) from poisoning the cache and causing
        every subsequent request to fail until the TTL expires.
    """
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            # Build a stable cache key
            key = f"{fn.__module__}.{fn.__qualname__}:{args!r}:{sorted(kwargs.items())!r}"
            now = time.monotonic()

            with _lock:
                entry = _cache.get(key)
                if entry is not None:
                    expires_at, value = entry
                    if now < expires_at:
                        return value

            # Compute OUTSIDE the lock so other threads can still read stale-but-valid
            # cache entries while this thread recomputes.
            # IMPORTANT: if fn() raises, the exception propagates here and the
            # write below is never reached — exceptions are never cached.
            value = fn(*args, **kwargs)

            with _lock:
                _cache[key] = (now + ttl_seconds, value)

            return value

        def invalidate(*args, **kwargs):
            """Manually invalidate a specific cache entry."""
            key = f"{fn.__module__}.{fn.__qualname__}:{args!r}:{sorted(kwargs.items())!r}"
            with _lock:
                _cache.pop(key, None)

        wrapper.invalidate = invalidate  # type: ignore[attr-defined]
        return wrapper

    return decorator


def clear_all() -> None:
    """Clear the entire cache. Useful in tests."""
    with _lock:
        _cache.clear()
