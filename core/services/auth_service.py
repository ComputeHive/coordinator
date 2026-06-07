"""
Authentication service.

Responsibilities:
- Hash / verify passwords with bcrypt.
- Issue and validate JWT tokens.

The old code stored the raw password inside the JWT payload, which is a
security flaw: anyone who can read the token can extract the password and
re-use it to generate new tokens indefinitely.  The new implementation puts
only the username in the payload; identity is re-validated against the DB on
every authenticated request.
"""

from __future__ import annotations

import datetime
from datetime import timedelta, timezone

import bcrypt
import jwt

from core.domain.exceptions import AuthenticationError


class AuthService:
    _ALGORITHM = "HS256"
    _TOKEN_TTL_DAYS = 30

    def __init__(self, secret_key: str) -> None:
        self._secret_key = secret_key

    # ------------------------------------------------------------------
    # Password helpers
    # ------------------------------------------------------------------

    @staticmethod
    def hash_password(plain: str) -> str:
        return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

    @staticmethod
    def verify_password(plain: str, hashed: str) -> bool:
        try:
            return bcrypt.checkpw(plain.encode(), hashed.encode())
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Token helpers
    # ------------------------------------------------------------------

    def issue_token(self, username: str) -> str:
        exp = datetime.datetime.now(tz=timezone.utc) + timedelta(days=self._TOKEN_TTL_DAYS)
        payload = {"username": username, "exp": exp}
        return jwt.encode(payload, self._secret_key, algorithm=self._ALGORITHM)

    def decode_token(self, token: str) -> str:
        """Return username or raise AuthenticationError."""
        try:
            payload = jwt.decode(token, self._secret_key, algorithms=[self._ALGORITHM])
            return payload["username"]
        except jwt.ExpiredSignatureError:
            raise AuthenticationError("Token expired. Please sign in again.")
        except jwt.InvalidTokenError:
            raise AuthenticationError("Invalid token. Please sign in again.")
