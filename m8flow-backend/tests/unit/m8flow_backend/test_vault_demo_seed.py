from __future__ import annotations

import importlib.util
from pathlib import Path


_SEED_SCRIPT = (
    Path(__file__).resolve().parents[3]
    .parent
    / "docker"
    / "vault"
    / "demo"
    / "seed_vault_demo.py"
)


def _seed_module():
    spec = importlib.util.spec_from_file_location("seed_vault_demo", _SEED_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_missing_demo_seed_log_does_not_reveal_configured_file_path(
    tmp_path, monkeypatch, capsys
):
    module = _seed_module()
    missing_path = tmp_path / "private-credential-seed.yml"
    monkeypatch.setattr(module, "SECRETS", missing_path)
    monkeypatch.setattr(
        module,
        "tenant_id_from_database",
        lambda: (_ for _ in ()).throw(AssertionError("seeding should stop before database access")),
    )

    assert module.seed() == (0, 0)
    output = capsys.readouterr().out
    assert "no local seed file found" in output
    assert str(missing_path) not in output
    assert "private-credential-seed" not in output
