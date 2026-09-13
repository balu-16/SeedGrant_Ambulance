"""Rate limiter client-IP keying: X-Forwarded-For is spoofable and must only be
honored behind a trusted proxy."""

import types

import app.middleware.rate_limit as rl
from app.middleware.rate_limit import RateLimitMiddleware


class _StubRequest:
    def __init__(self, host: str, xff: str | None):
        self.headers = {"x-forwarded-for": xff} if xff else {}
        self.client = types.SimpleNamespace(host=host)


def _with_settings(monkeypatch, trust: bool):
    stub = types.SimpleNamespace(TRUST_PROXY_HEADERS=trust)
    monkeypatch.setattr(rl, "get_settings", lambda: stub)


def test_spoofed_xff_ignored_by_default(monkeypatch):
    """Direct exposure (default): the attacker-controlled header must not key buckets."""
    _with_settings(monkeypatch, trust=False)
    req = _StubRequest("203.0.113.9", "1.2.3.4")
    assert RateLimitMiddleware._client_ip(req) == "203.0.113.9"
    # different XFF values, same socket peer → one bucket
    assert RateLimitMiddleware._client_ip(_StubRequest("203.0.113.9", "5.6.7.8")) == "203.0.113.9"


def test_xff_honored_only_when_trusted(monkeypatch):
    _with_settings(monkeypatch, trust=True)
    assert RateLimitMiddleware._client_ip(_StubRequest("10.0.0.1", "1.2.3.4, 10.0.0.1")) == (
        "1.2.3.4"
    )
    assert RateLimitMiddleware._client_ip(_StubRequest("10.0.0.1", None)) == "10.0.0.1"
