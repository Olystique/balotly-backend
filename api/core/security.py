"""Cryptographic primitives: vault, secret hashing, password hashing.

Two distinct hashing concerns live here, deliberately kept apart:

* ``hash_secret``   — deterministic SHA-256. For values we need to *look up* by
  hash. Fast and unsalted by design.
* ``hash_password`` — salted bcrypt. For user passwords. Slow by design.

Never substitute one for the other.

The vault (``encrypt_str`` / ``decrypt_str``) holds bank account numbers at
rest. A candidate's account number is not a credential, but it is exactly the
personal financial detail the manual poster-plus-transfer flow leaked to every
voter, and a database dump must not leak it the same way.
"""

import base64
import functools
import hashlib
import hmac
import secrets

import bcrypt
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from api.utils.settings import settings

# AES-GCM standard nonce length. Prepended to every ciphertext blob.
_NONCE_BYTES = 12
_KEY_BYTES = 32  # AES-256


@functools.lru_cache(maxsize=1)
def _key() -> bytes:
    """Decode and validate the vault key.

    Resolved lazily (not at import) so that a missing key surfaces as a clear
    error when crypto is first used, rather than breaking module import.
    """
    try:
        raw = base64.b64decode(settings.ENCRYPTION_KEY, validate=True)
    except Exception as exc:  # noqa: BLE001 - re-raised with actionable guidance
        raise ValueError(
            "ENCRYPTION_KEY is not valid base64. Generate one with: "
            'python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"'
        ) from exc

    if len(raw) != _KEY_BYTES:
        raise ValueError(
            f"ENCRYPTION_KEY must decode to exactly {_KEY_BYTES} bytes "
            f"(AES-256), got {len(raw)}."
        )
    return raw


def encrypt_bytes(plaintext: bytes) -> bytes:
    """Encrypt with AES-256-GCM. Returns ``nonce || ciphertext || tag``.

    A fresh nonce per call is mandatory for GCM — reusing one against the same
    key breaks confidentiality *and* authentication.
    """
    nonce = secrets.token_bytes(_NONCE_BYTES)
    return nonce + AESGCM(_key()).encrypt(nonce, plaintext, None)


def decrypt_bytes(blob: bytes) -> bytes:
    """Reverse of :func:`encrypt_bytes`.

    Raises ``InvalidTag`` if the blob was tampered with or encrypted under a
    different key. Callers should treat that as a hard failure, not a miss.
    """
    if len(blob) <= _NONCE_BYTES:
        raise InvalidTag("Ciphertext too short to contain a nonce.")
    nonce, ciphertext = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
    return AESGCM(_key()).decrypt(nonce, ciphertext, None)


def encrypt_str(plaintext: str) -> bytes:
    return encrypt_bytes(plaintext.encode())


def decrypt_str(blob: bytes) -> str:
    return decrypt_bytes(blob).decode()


def hash_secret(secret: str) -> str:
    """Deterministic SHA-256 hex digest — for hash-based *lookup*, not passwords."""
    return hashlib.sha256(secret.encode()).hexdigest()


def hash_short_code(code: str) -> str:
    """Keyed digest for a short numeric code.

    Plain SHA-256 is right for a 256-bit token and wrong for a six-digit one:
    the entire input space is a million values, so anyone holding a database
    backup could reverse every stored digest in under a second by hashing all
    of them. Keying the digest with ``SECRET_KEY`` means the backup alone is
    not enough, because the attacker also needs a secret that lives in the
    environment rather than the database.

    Deterministic, so lookup still works, and constant-time comparison is the
    caller's job.
    """
    return hmac.new(
        settings.SECRET_KEY.encode(), code.encode(), hashlib.sha256
    ).hexdigest()


def generate_secret(prefix: str) -> str:
    """Generate a prefixed, URL-safe random secret, e.g. ``pk_xTf9...``."""
    return f"{prefix}_{secrets.token_urlsafe(32)}"


def _prehash(password: str) -> bytes:
    """SHA-256 -> base64 before bcrypt.

    bcrypt silently truncates input at 72 bytes, so a long passphrase would
    only be validated up to that point. Pre-hashing normalises every password
    to 44 bytes and removes the limit. Applied on both hash and verify, so the
    two stay consistent.
    """
    return base64.b64encode(hashlib.sha256(password.encode()).digest())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prehash(password), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_prehash(password), password_hash.encode())
    except (ValueError, TypeError):
        # Malformed/legacy hash in the DB — treat as a failed login, not a 500.
        return False


@functools.lru_cache(maxsize=1)
def _decoy_password_hash() -> str:
    """A real bcrypt hash of an unguessable secret, generated once per process.

    Resolved lazily rather than at import for the same reason as :func:`_key`,
    and because generating it costs a full bcrypt round.
    """
    return hash_password(generate_secret("decoy"))


def verify_password_equal_time(password: str, password_hash: str | None) -> bool:
    """Verify a password, spending the same time when the account is absent.

    Returning early for an unknown email would make a failed login measurably
    faster than a wrong password against a real account — which hands an
    attacker the account enumeration that an identical error message is meant
    to deny. So a missing hash is checked against a decoy of equal cost and the
    answer is discarded.

    ``password_hash`` is ``None`` only when no user was found; a real hash is
    verified exactly as :func:`verify_password` would.
    """
    if password_hash is None:
        verify_password(password, _decoy_password_hash())
        return False
    return verify_password(password, password_hash)
