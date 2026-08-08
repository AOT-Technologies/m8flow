from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path


def test_vault_metadata_timestamps_are_available_from_startup_bootstrap() -> None:
    repo_root = Path(__file__).resolve().parents[5]
    script = textwrap.dedent(
        """
        import sys
        from pathlib import Path

        from flask import Flask

        repo_root = Path.cwd()
        extension_root = repo_root / "m8flow-backend"
        extension_src = extension_root / "src"
        backend_src = repo_root / "spiffworkflow-backend" / "src"

        for path in (repo_root, extension_src, backend_src):
            path_str = str(path)
            if path_str not in sys.path:
                sys.path.insert(0, path_str)

        from m8flow_backend.bootstrap import ensure_m8flow_audit_timestamps
        from m8flow_backend.models.m8flow_tenant import M8flowTenantModel, TenantStatus
        from spiffworkflow_backend.models.db import add_listeners, db
        from spiffworkflow_backend.models.user import UserModel

        app = Flask(__name__)
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
        app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
        db.init_app(app)

        with app.app_context():
            db.create_all()
            add_listeners()

            tenant = M8flowTenantModel(
                id="tenant-1",
                name="Tenant One",
                slug="tenant-one",
                status=TenantStatus.ACTIVE,
                created_by="system",
                modified_by="system",
            )
            user = UserModel(
                username="alice",
                email="alice@example.com",
                service="local",
                service_id="alice",
            )
            db.session.add_all([tenant, user])
            db.session.commit()

            ensure_m8flow_audit_timestamps()

            from m8flow_backend.models.vault_metadata import VaultMetadataModel

            db.create_all()

            row = VaultMetadataModel(
                id="meta-1",
                name="API_TOKEN",
                user_id=user.id,
                created_by="alice",
                modified_by="alice",
                m8f_tenant_id=tenant.id,
            )
            db.session.add(row)
            db.session.commit()

            assert isinstance(row.created_at_in_seconds, int)
            assert row.created_at_in_seconds > 0
            assert isinstance(row.updated_at_in_seconds, int)
            assert row.updated_at_in_seconds > 0

            before_update = row.updated_at_in_seconds
            row.modified_by = "bob"
            db.session.commit()
            assert row.updated_at_in_seconds >= before_update
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, f"subprocess failed\\nstdout:\\n{result.stdout}\\nstderr:\\n{result.stderr}"
