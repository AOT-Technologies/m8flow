from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import textwrap


def test_importing_tenant_scoping_patch_does_not_preload_spiff_models() -> None:
    repo_root = Path(__file__).resolve().parents[5]
    backend_root = repo_root / "m8flow-backend"
    extension_src = backend_root / "src"
    upstream_src = repo_root / "spiffworkflow-backend" / "src"

    script = textwrap.dedent(
        f"""
        import importlib
        import sys

        for path in {[
            str(repo_root),
            str(extension_src),
            str(upstream_src),
        ]!r}:
            if path not in sys.path:
                sys.path.insert(0, path)

        importlib.import_module("m8flow_backend.services.tenant_scoping_patch")

        loaded = sorted(name for name in sys.modules if name.startswith("spiffworkflow_backend.models"))
        assert not loaded, loaded
        """
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
