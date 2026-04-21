"""Security utilities for authentication and authorization."""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from uuid import uuid4, UUID

from jose import JWTError, jwt
import bcrypt

from src.config import settings


def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt."""
    # Ensure password is bytes
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    password_bytes = plain_password.encode('utf-8')
    hashed_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_bytes, hashed_bytes)


def create_access_token(
    user_id: UUID,
    expires_delta: Optional[timedelta] = None,
    extra_claims: Optional[Dict[str, Any]] = None,
) -> str:
    """Create a new access token."""
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

    expire = datetime.utcnow() + expires_delta

    payload = {
        "sub": str(user_id),
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access",
        "jti": str(uuid4()),
    }

    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(
        payload,
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )


def create_refresh_token(
    user_id: UUID,
    token_id: Optional[UUID] = None,
    expires_delta: Optional[timedelta] = None,
) -> tuple[str, UUID]:
    """Create a new refresh token.

    Returns:
        Tuple of (token_string, token_id)
    """
    if expires_delta is None:
        expires_delta = timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)

    if token_id is None:
        token_id = uuid4()

    expire = datetime.utcnow() + expires_delta

    payload = {
        "sub": str(user_id),
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "refresh",
        "jti": str(token_id),
    }

    token = jwt.encode(
        payload,
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )

    return token, token_id


def decode_token(token: str, verify_exp: bool = True) -> Optional[Dict[str, Any]]:
    """Decode and validate a JWT token.

    Returns:
        Decoded payload or None if invalid.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_exp": verify_exp},
        )
        return payload
    except JWTError:
        return None


def verify_token_type(payload: Dict[str, Any], expected_type: str) -> bool:
    """Verify the token type in payload."""
    return payload.get("type") == expected_type
