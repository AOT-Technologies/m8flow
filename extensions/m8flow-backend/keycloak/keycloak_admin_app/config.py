"""Configuration from environment for Keycloak admin app."""
import os
from pathlib import Path

# Keycloak
KEYCLOAK_URL = os.environ.get("KEYCLOAK_URL", "http://localhost:7002").rstrip("/")
REALM = os.environ.get("KEYCLOAK_REALM", "tenant-a")
ADMIN_USER = os.environ.get("KEYCLOAK_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("KEYCLOAK_ADMIN_PASSWORD", "admin")

# Client used for admin API (service account / client credentials)
# Use either client_secret or certificate + key for mTLS
CLIENT_ID = os.environ.get("KEYCLOAK_CLIENT_ID", "my-backend-app")
CLIENT_SECRET = os.environ.get("KEYCLOAK_CLIENT_SECRET", "")

# Certificate auth (mTLS): paths to cert and key from Keycloak client (m8-backend / my-backend-app)
CERT_FILE = os.environ.get("KEYCLOAK_CERT_FILE", "")
KEY_FILE = os.environ.get("KEYCLOAK_KEY_FILE", "")

# Fallback: look for certificate.pem / key.pem in script dir
_APP_DIR = Path(__file__).resolve().parent
if not CERT_FILE and (_APP_DIR / "certificate.pem").exists():
    CERT_FILE = str(_APP_DIR / "certificate.pem")
if not KEY_FILE and (_APP_DIR / "key.pem").exists():
    KEY_FILE = str(_APP_DIR / "key.pem")


def use_cert_auth() -> bool:
    return bool(CERT_FILE and KEY_FILE and Path(CERT_FILE).exists() and Path(KEY_FILE).exists())


def use_secret_auth() -> bool:
    return bool(CLIENT_SECRET)
