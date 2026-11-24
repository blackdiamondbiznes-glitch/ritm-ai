"""Email account validation and password hashing for EduFlow sign-in."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets

EMAIL_MAX = 254
PASSWORD_MIN = 10
PASSWORD_MAX = 256
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}$")
_ROLES = frozenset({"teacher", "student", "community_owner"})
_SCRYPT_N = 1 << 14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_BYTES = 32


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
    """Create a salted scrypt hash; plaintext is never stored."""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_BYTES,
    )
    return "scrypt${}${}${}".format(
        _SCRYPT_N,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, encoded: str | None) -> bool:
    """Verify a stored scrypt hash without revealing which check failed."""
    if not encoded:
        return False
    try:
        algorithm, n_s, salt_s, digest_s = encoded.split("$")
        if algorithm != "scrypt" or int(n_s) != _SCRYPT_N:
            return False
        salt = base64.urlsafe_b64decode(salt_s.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_s.encode("ascii"))
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=_SCRYPT_N,
            r=_SCRYPT_R,
            p=_SCRYPT_P,
            dklen=len(expected),
        )
    except (ValueError, TypeError, UnicodeError):
        return False
    return hmac.compare_digest(actual, expected)
