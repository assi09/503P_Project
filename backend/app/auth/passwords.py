"""Password hashing with scrypt from the standard library, so no extra dependency.

Hashes are stored as `scrypt$n$r$p$salt$digest` (base64 parts): the cost travels with each hash,
so it can be raised later and older hashes still verify.
"""

import base64
import hashlib
import hmac
import secrets

# About 16 MB and tens of milliseconds per hash: slow for guessing, fine for a login.
N, R, P = 2**14, 8, 1
DIGEST_BYTES = 32


def _encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P, dklen=DIGEST_BYTES)
    return f"scrypt${N}${R}${P}${_encode(salt)}${_encode(digest)}"


def verify_password(password: str, stored: str) -> bool:
    """True when `password` matches; False for a wrong password or a malformed hash."""
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        candidate = hashlib.scrypt(
            password.encode(),
            salt=base64.b64decode(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except ValueError:
        return False
    return hmac.compare_digest(candidate, expected)


# Verified against when the email is unknown, so a login takes as long either way and the
# timing does not reveal who has an account.
DUMMY_HASH = hash_password(secrets.token_hex(16))
