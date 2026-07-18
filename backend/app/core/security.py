"""Password hashing and JWT token primitives."""

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from .config import Settings

_password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenError(ValueError):
    """Raised when a token cannot be created or verified."""


class SecurityService:
    """Stateless JWT and password operations used by authentication services."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def hash_password(self, password: str) -> str:
        """Hash a validated password using bcrypt."""
        return _password_context.hash(password)

    def verify_password(self, password: str, hashed_password: str) -> bool:
        """Verify a password against a bcrypt hash."""
        return _password_context.verify(password, hashed_password)

    def create_access_token(self, subject: str, role: str) -> str:
        """Create a signed, short-lived access token."""
        expires = timedelta(minutes=self._settings.access_token_expire_minutes)
        return self._encode_token(subject, role, "access", expires)

    def create_refresh_token(self, subject: str, role: str) -> str:
        """Create a signed refresh token."""
        expires = timedelta(days=self._settings.refresh_token_expire_days)
        return self._encode_token(subject, role, "refresh", expires)

    def decode_token(self, token: str, expected_type: str) -> dict[str, Any]:
        """Verify a token and ensure it has the expected token type."""
        try:
            payload = jwt.decode(token, self._secret, algorithms=[self._settings.jwt_algorithm])
        except JWTError as error:
            raise TokenError("Invalid or expired token.") from error
        if payload.get("token_type") != expected_type or not payload.get("sub"):
            raise TokenError("Invalid token claims.")
        return payload

    @property
    def _secret(self) -> str:
        if self._settings.jwt_secret_key is None:
            raise TokenError("JWT_SECRET_KEY is not configured.")
        return self._settings.jwt_secret_key.get_secret_value()

    def _encode_token(self, subject: str, role: str, token_type: str, expires: timedelta) -> str:
        now = datetime.now(timezone.utc)
        payload = {"sub": subject, "role": role, "token_type": token_type, "iat": now, "exp": now + expires}
        return jwt.encode(payload, self._secret, algorithm=self._settings.jwt_algorithm)
