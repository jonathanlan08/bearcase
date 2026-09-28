"""Spare Northstar demo identities built ahead of visitors.

Seeding a demo runs the whole pipeline (seven documents, analysis, report): a quarter of a second on a laptop, but
several seconds on a small host where every one of its ~600 statements crosses the network to the database. The
pool keeps `demo_pool_size` finished identities ready; /api/demo/session hands one out and schedules a refill.
"""

from __future__ import annotations

import logging
import threading

from bearcase.auth import create_spare_demo_identity, spare_demo_count
from bearcase.config import get_settings
from bearcase.db import get_session_factory
from bearcase.seed import seed_northstar

log = logging.getLogger("bearcase.demo_pool")
_refill_lock = threading.Lock()


def refill_demo_pool() -> int:
    """Build spares until the pool is full. One refill runs per process at a time; a call that finds another in
    progress returns at once. Failures are logged and never raised: a visitor then simply gets a seeded deal."""
    size = get_settings().demo_pool_size
    if size <= 0 or not _refill_lock.acquire(blocking=False):
        return 0
    built = 0
    try:
        for _ in range(size):
            with get_session_factory()() as db:
                if spare_demo_count(db) >= size:
                    break
                seed_northstar(db, create_spare_demo_identity(db))
                db.commit()
                built += 1
    except Exception:
        log.exception("demo pool refill failed")
    finally:
        _refill_lock.release()
    if built:
        log.info("built %d spare demo identit%s", built, "y" if built == 1 else "ies")
    return built
