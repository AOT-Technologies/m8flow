from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Point m8flow-backend pyproject/uv.lock at a staged m8flow-bpmn-core wheel."
    )
    parser.add_argument("--pyproject-path", required=True)
    parser.add_argument("--uv-lock-path", required=True)
    parser.add_argument("--wheel-path", required=True)
    parser.add_argument("--uv-executable", default="uv")
    args = parser.parse_args()

    pyproject_path = Path(args.pyproject_path)
    uv_lock_path = Path(args.uv_lock_path)
    wheel_path = Path(args.wheel_path)
    relative_wheel_path = f"vendor/{wheel_path.name}"

    original_text = pyproject_path.read_text(encoding="utf-8")
    updated_text, substitutions = re.subn(
        r'm8flow-bpmn-core = \{ path = "vendor/[^"]+" \}',
        f'm8flow-bpmn-core = {{ path = "{relative_wheel_path}" }}',
        original_text,
        count=1,
    )
    if substitutions != 1:
        raise RuntimeError(f"Could not update '{pyproject_path}' with the staged wheel path.")
    pyproject_path.write_text(updated_text, encoding="utf-8")

    uv_command = args.uv_executable
    if not Path(uv_command).exists():
        resolved = shutil.which(uv_command)
        if resolved is None:
            raise RuntimeError("Could not find the 'uv' executable.")
        uv_command = resolved

    subprocess.run(
        [uv_command, "lock"],
        check=True,
        cwd=pyproject_path.parent,
    )
    if not uv_lock_path.exists():
        raise RuntimeError(f"uv lock did not create '{uv_lock_path}'.")
    _ = hashlib.sha256(wheel_path.read_bytes()).hexdigest()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
