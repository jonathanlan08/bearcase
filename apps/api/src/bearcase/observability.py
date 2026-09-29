"""Optional error tracking with Sentry.

Off unless `SENTRY_DSN` is set in the environment (Render dashboard), so development, tests, and a deployment
without an account behave exactly as before. When on, it reports unhandled exceptions only: no performance
tracing (keeps a free plan's quota for errors), no request bodies, no cookies or auth headers, and no local
variables from stack frames, because frames can hold document text or a provider key.
"""

from __future__ import annotations

import os

from bearcase import __version__


def init_sentry() -> bool:
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return False
    import sentry_sdk

    sentry_sdk.init(
        dsn=dsn,
        environment=os.environ.get("BEARCASE_ENV", "development"),
        release=f"bearcase-api@{__version__}",
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size="never",
        traces_sample_rate=0.0,
    )
    return True
