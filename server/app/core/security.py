from datetime import UTC, datetime, timedelta

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError
from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher

from app.core.config import get_settings

_ph = PasswordHash((BcryptHasher(),))


def hash_password(p: str) -> str:
    if len(p.encode()) > 72:
        raise ValueError("Password too long (max 72 bytes for bcrypt)")
    return _ph.hash(p)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _ph.verify(plain, hashed)
    except Exception:
        return False


def _encode(payload: dict, expires: timedelta) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload = {
        **payload,
        "iat": now,
        "exp": now + expires,
        "iss": s.JWT_ISSUER,
        "aud": s.JWT_AUDIENCE,
    }
    return jwt.encode(payload, s.JWT_SECRET, algorithm=s.JWT_ALGORITHM)


def create_access_token(sub: str, role: str) -> str:
    s = get_settings()
    return _encode(
        {"sub": sub, "role": role, "type": "access"},
        timedelta(minutes=s.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(sub: str, version: int = 0) -> str:
    s = get_settings()
    return _encode(
        {"sub": sub, "type": "refresh", "ver": version},
        timedelta(days=s.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str) -> dict:
    """Decode + verify signature/expiry/iss/aud. Raises Unauthorized on any failure."""
    from app.core.exceptions import Unauthorized

    s = get_settings()
    try:
        return jwt.decode(
            token,
            s.JWT_SECRET,
            algorithms=[s.JWT_ALGORITHM],
            issuer=s.JWT_ISSUER,
            audience=s.JWT_AUDIENCE,
        )
    except ExpiredSignatureError:
        raise Unauthorized("Token expired") from None
    except InvalidTokenError:
        raise Unauthorized("Invalid token") from None
