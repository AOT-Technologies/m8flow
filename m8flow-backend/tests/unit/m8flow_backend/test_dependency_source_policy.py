import subprocess
import sys
from pathlib import Path


_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
_CHECK_SCRIPT = _REPOSITORY_ROOT / "bin" / "compliance" / "check_local_wheel_sources.py"


def _run_policy_check(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_CHECK_SCRIPT), "--root", str(root)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_local_wheel_path_in_project_and_lock_is_rejected(tmp_path):
    backend = tmp_path / "m8flow-backend"
    backend.mkdir()
    (backend / "pyproject.toml").write_text(
        '[tool.uv.sources]\nm8flow-core = { path = "local_wheels/m8flow_core.whl" }\n',
        encoding="utf-8",
    )
    (backend / "uv.lock").write_text(
        'source = { path = "local_wheels/m8flow_core.whl" }\n',
        encoding="utf-8",
    )

    result = _run_policy_check(tmp_path)

    assert result.returncode == 1
    normalized_output = result.stdout.replace("\\", "/")
    assert "m8flow-backend/pyproject.toml:2" in normalized_output
    assert "m8flow-backend/uv.lock:1" in normalized_output


def test_registry_dependency_and_local_non_wheel_source_are_allowed(tmp_path):
    backend = tmp_path / "m8flow-backend"
    backend.mkdir()
    (backend / "pyproject.toml").write_text(
        '[project]\ndependencies = ["m8flow-core==1.0.0b3"]\n'
        '[tool.uv.sources]\nm8flow-telemetry = { path = "../m8flow-telemetry" }\n',
        encoding="utf-8",
    )

    result = _run_policy_check(tmp_path)

    assert result.returncode == 0
    assert "No local wheel sources found" in result.stdout


def test_committed_node_wire_vendor_wheel_source_is_allowed(tmp_path):
    proxy = tmp_path / "m8flow-node-wire-proxy"
    wheels = proxy / "vendor" / "wheels"
    wheels.mkdir(parents=True)
    (wheels / "node_wire_runtime.whl").write_bytes(b"fixture")
    (proxy / "pyproject.toml").write_text(
        '[tool.uv.sources]\nnode-wire-runtime = { path = "vendor/wheels/node_wire_runtime.whl" }\n',
        encoding="utf-8",
    )

    result = _run_policy_check(tmp_path)

    assert result.returncode == 0
