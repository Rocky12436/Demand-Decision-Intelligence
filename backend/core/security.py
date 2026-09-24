import bcrypt
from datetime import datetime, timedelta, timezone
from typing import Optional, Any, Dict
import jwt
from backend.core.config import settings

# Server-side pinned algorithm (do not accept dynamic alg header)
PINNED_ALGORITHM = "HS256"


# ──────────────────────────────────────────────
# Password utilities
# ──────────────────────────────────────────────

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Compare a plain-text password against its bcrypt hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8")
        )
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    """Return a bcrypt hash for the given password (max 72 bytes)."""
    pwd_bytes = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pwd_bytes, bcrypt.gensalt()).decode("utf-8")


# ──────────────────────────────────────────────
# JWT utilities (Pinned HS256, 32+ byte secret)
# ──────────────────────────────────────────────

def create_access_token(
    subject: str | Any,
    role: Optional[str] = None,
    expires_delta: Optional[timedelta] = None
) -> str:
    """Encode a short-lived JWT access token with pinned HS256."""
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    to_encode: Dict[str, Any] = {
        "exp": expire,
        "sub": str(subject),
        "token_type": "access",
    }
    if role:
        to_encode["role"] = role
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=PINNED_ALGORITHM)


def create_refresh_token(
    subject: str | Any,
    expires_delta: Optional[timedelta] = None
) -> str:
    """Encode a longer-lived JWT refresh token with pinned HS256."""
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        )
    to_encode: Dict[str, Any] = {
        "exp": expire,
        "sub": str(subject),
        "token_type": "refresh",
    }
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=PINNED_ALGORITHM)


def decode_access_token(token: str) -> Optional[str]:
    """
    Decode an access JWT with strictly pinned algorithm and validate expiration.
    Returns the `sub` claim on success, or None on failure.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[PINNED_ALGORITHM],
            options={"require": ["exp", "sub"]}
        )
        if payload.get("token_type") not in ("access", None):
            return None
        return payload.get("sub")
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def decode_refresh_token(token: str) -> Optional[str]:
    """
    Decode a refresh JWT with strictly pinned algorithm and validate expiration.
    Returns the `sub` claim on success, or None on failure.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[PINNED_ALGORITHM],
            options={"require": ["exp", "sub"]}
        )
        if payload.get("token_type") != "refresh":
            return None
        return payload.get("sub")
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None
