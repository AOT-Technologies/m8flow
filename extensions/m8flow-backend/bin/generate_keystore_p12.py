#!/usr/bin/env python3
"""
Generate a PKCS#12 keystore (keystore.p12) for M8Flow Keycloak spoke client JWT authentication.

Used by m8flow_backend.config.spoke_keystore_p12_path() and keycloak_service (client assertion).
Run manually from the repo root with the backend venv active so 'cryptography' is available.

  From repo root:
    python extensions/m8flow-backend/bin/generate_keystore_p12.py
    python extensions/m8flow-backend/bin/generate_keystore_p12.py -o /path/to/keystore.p12
  Optional env:
    M8FLOW_KEYCLOAK_SPOKE_KEYSTORE_PASSWORD  (or pass -p / --password)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate PKCS#12 keystore for M8Flow Keycloak spoke client JWT auth."
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output path for keystore.p12 (default: extensions/m8flow-backend/keystore.p12 from cwd)",
    )
    parser.add_argument(
        "-p",
        "--password",
        default=None,
        help="Keystore password (default: M8FLOW_KEYCLOAK_SPOKE_KEYSTORE_PASSWORD env, or prompt)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=365,
        help="Validity of the self-signed certificate in days (default: 365)",
    )
    parser.add_argument(
        "--cn",
        default="spiffworkflow-backend",
        help="Common name for the certificate subject (default: spiffworkflow-backend)",
    )
    args = parser.parse_args()

    try:
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.serialization import pkcs12
        from cryptography import x509
        from cryptography.x509.oid import NameOID
    except ImportError as e:
        print("Error: 'cryptography' is required. Activate the backend venv and run again.", file=sys.stderr)
        print(f"  {e}", file=sys.stderr)
        return 1

    out = args.output
    if not out:
        out = Path.cwd() / "extensions" / "m8flow-backend" / "keystore.p12"
    else:
        out = Path(out)
    out = out.resolve()

    password = args.password or os.environ.get("M8FLOW_KEYCLOAK_SPOKE_KEYSTORE_PASSWORD")
    if not password:
        import getpass
        password = getpass.getpass("Keystore password: ")
        if not password:
            print("Error: empty password.", file=sys.stderr)
            return 1
    pw_bytes = password.encode("utf-8")

    # Generate RSA private key
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    # Self-signed certificate
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, args.cn),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "M8Flow"),
    ])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=args.days))
        .sign(key, hashes.SHA256())
    )

    # PKCS#12: key + cert (no extra CA chain)
    p12_bytes = pkcs12.serialize_key_and_certificates(
        name=args.cn.encode("utf-8"),
        key=key,
        cert=cert,
        cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(pw_bytes),
    )

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(p12_bytes)
    print(f"Wrote {out}")
    print("Set M8FLOW_KEYCLOAK_SPOKE_KEYSTORE_P12 to this path and M8FLOW_KEYCLOAK_SPOKE_KEYSTORE_PASSWORD to the password.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
