"""Portal access-token claims (contract §1) — pure unit test."""

import datetime as _dt

import jwt as pyjwt

from app.core.config import get_settings
from app.core.security import create_portal_access_token


def test_portal_access_token_carries_sid_claim():
    """Portal JWT claims are {sub, sid, type:'access'} (contract §1)."""
    token = create_portal_access_token("11111111-1111-1111-1111-111111111111",
                                       "22222222-2222-2222-2222-222222222222")
    s = get_settings()
    payload = pyjwt.decode(
        token, s.JWT_SECRET, algorithms=["HS256"],
        issuer=s.JWT_ISSUER, audience=s.JWT_AUDIENCE,
    )
    assert payload["sub"] == "11111111-1111-1111-1111-111111111111"
    assert payload["sid"] == "22222222-2222-2222-2222-222222222222"
    assert payload["type"] == "access"
    # expiry = PORTAL_ACCESS_TOKEN_MINUTES
    exp = _dt.datetime.fromtimestamp(payload["exp"], tz=_dt.UTC)
    now = _dt.datetime.fromtimestamp(payload["iat"], tz=_dt.UTC)
    assert exp - now == _dt.timedelta(minutes=s.PORTAL_ACCESS_TOKEN_MINUTES)
