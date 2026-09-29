"""Sentry stays off without a DSN, and when on it never ships request bodies, PII, or frame locals."""

from __future__ import annotations

import sentry_sdk

from bearcase.observability import init_sentry


def test_off_without_a_dsn(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    assert init_sentry() is False


def test_on_with_a_dsn_and_private_by_default(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTRY_DSN", "https://public@o0.ingest.sentry.io/0")
    try:
        assert init_sentry() is True
        options = sentry_sdk.get_client().options
        assert options["send_default_pii"] is False
        assert options["include_local_variables"] is False
        assert options["max_request_body_size"] == "never"
        assert options["traces_sample_rate"] == 0.0
    finally:
        sentry_sdk.init(dsn=None)  # back to a disabled client for the rest of the suite
