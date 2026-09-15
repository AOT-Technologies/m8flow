"""Host-owned at-rest encryption for the database secret provider.

Fernet key is HKDF-derived from ``M8FLOW_SECRETS_ENCRYPTION_KEY``, falling back
to ``FLASK_SESSION_SECRET_KEY``. Ciphertext is stored; plaintext is never the
on-disk form for new writes. Legacy plaintext rows (pre-encryption) still
decrypt as themselves so existing test fixtures keep working.
"""

from __future__ import annotations

import base64
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from m8flow_backend.startup.env_var_mapper import is_unit_testing_environment

_SALT = b"m8flow-secrets-v1"
_INFO = b"secret-at-rest"
_FALLBACK_MATERIAL = "unit-test-secret-key-32bytes-min"


def _secret_material() -> bytes:
    material = (
        os.environ.get("M8FLOW_SECRETS_ENCRYPTION_KEY")
        or os.environ.get("FLASK_SESSION_SECRET_KEY")
        or ""
    ).strip()
    if material:
        return material.encode("utf-8")
    if is_unit_testing_environment():
        return _FALLBACK_MATERIAL.encode("utf-8")
    raise RuntimeError(
        "M8FLOW_SECRETS_ENCRYPTION_KEY or FLASK_SESSION_SECRET_KEY must be set "
        "outside unit-testing environments."
    )


def _fernet() -> Fernet:
    derived = HKDF(algorithm=hashes.SHA256(), length=32, salt=_SALT, info=_INFO).derive(
        _secret_material()
    )
    return Fernet(base64.urlsafe_b64encode(derived))


def encrypt_secret_value(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret_value(stored: str) -> str:
    try:
        return _fernet().decrypt(stored.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return stored
