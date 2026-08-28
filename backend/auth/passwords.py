"""Password hashing (Day 1 design.md Decision 5 deferred the algorithm to Day 6).

argon2id via ``argon2-cffi``: the OWASP-recommended default, parameters left at the
library's defaults (64 MiB, 3 passes, 4 lanes), no 72-byte input limit to police as with
bcrypt, and it installs on Python 3.14 -- ``passlib`` no longer imports there.
"""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# Argon2 itself accepts any length; the cap bounds the memory-hard work an anonymous
# caller can trigger per request. Shared with the request schema.
MAX_PASSWORD_LENGTH = 128
MIN_PASSWORD_LENGTH = 8

_hasher = PasswordHasher()

# A real hash of a throwaway value, verified against on login when the email is unknown so
# that "no such account" and "wrong password" take the same time.
_DUMMY_HASH = _hasher.hash("not-a-real-password")


def hash_password(password: str) -> str:
    """An encoded argon2id hash (salt and parameters included; fits ``String(255)``)."""
    return _hasher.hash(password)


def verify_password(hashed: str | None, password: str) -> bool:
    """True only if ``password`` produced ``hashed``.

    ``None`` runs the check against a dummy hash and returns False, keeping the timing of
    an unknown email indistinguishable from a wrong password.
    """
    try:
        return _hasher.verify(hashed if hashed is not None else _DUMMY_HASH, password) and (
            hashed is not None
        )
    except VerifyMismatchError, VerificationError, InvalidHashError:
        return False
