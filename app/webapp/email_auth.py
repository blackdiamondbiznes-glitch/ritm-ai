"""Email account validation and password hashing for EduFlow sign-in."""

from __future__ import annotations

import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

EMAIL_MAX = 254
PASSWORD_MIN = 10
PASSWORD_MAX = 256
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}$")
_ROLES = frozenset({"teacher", "student", "community_owner"})
_PASSWORD_HASHER = PasswordHasher()


class EmailAccountError(ValueError):
    """Invalid email-account input with a stable API error code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def normalize_email(value: object) -> str:
    """Validate and canonicalize an email address."""
    if not isinstance(value, str):
        raise EmailAccountError("email")
    email = value.strip().casefold()
    if len(email) > EMAIL_MAX or not _EMAIL.fullmatch(email):
        raise EmailAccountError("email")
    return email


def validate_signup(name: object, password: object, role: object) -> tuple[str, str, str]:
    """Validate fields shared by email sign-up."""
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 120:
        raise EmailAccountError("name")
    if not isinstance(password, str) or not PASSWORD_MIN <= len(password) <= PASSWORD_MAX:
        raise EmailAccountError("password")
    if not isinstance(role, str) or role not in _ROLES:
        raise EmailAccountError("role")
    return name.strip(), password, role


def hash_password(password: str) -> str:
    """Create an Argon2id hash; plaintext is never stored."""
    return _PASSWORD_HASHER.hash(password)


def verify_password(password: str, encoded: str | None) -> bool:
    """Verify a stored Argon2id hash without revealing which check failed."""
    if not encoded:
        return False
    try:
        return _PASSWORD_HASHER.verify(encoded, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False
