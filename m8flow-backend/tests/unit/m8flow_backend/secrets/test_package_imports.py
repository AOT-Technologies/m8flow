import subprocess
import sys


def test_provisioning_import_does_not_eagerly_import_vault_provider():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys
import m8flow_backend.secrets.provisioning
assert 'm8flow_backend.secrets.vault' not in sys.modules

from m8flow_backend.secrets.provider import get_secret_provider
assert type(get_secret_provider('vault')).__name__ == 'VaultSecretProvider'
""",
        ],
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
