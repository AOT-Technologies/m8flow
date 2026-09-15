#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
backend_dir="$(cd "$script_dir/.." && pwd)"
dist_dir="${1:-"$script_dir/../../../m8flow-bpmn-core/dist"}"
vendor_dir="$backend_dir/vendor"
pyproject_path="$backend_dir/pyproject.toml"
uv_lock_path="$backend_dir/uv.lock"
metadata_script="$script_dir/update_local_wheel_metadata.py"

wheel_path="$(ls -1t "$dist_dir"/m8flow_bpmn_core-*.whl 2>/dev/null | head -n 1 || true)"

if [[ -z "${wheel_path}" ]]; then
  echo "No m8flow_bpmn_core wheel was found in '$dist_dir'. Run 'uv build --wheel' in m8flow-bpmn-core first." >&2
  exit 1
fi

mkdir -p "$vendor_dir"
rm -f "$vendor_dir"/m8flow_bpmn_core-*.whl
destination="$vendor_dir/$(basename "$wheel_path")"
cp "$wheel_path" "$destination"

python3 "$metadata_script" \
  --pyproject-path "$pyproject_path" \
  --uv-lock-path "$uv_lock_path" \
  --wheel-path "$destination" \
  --uv-executable "uv"

echo "Staged wheel: $wheel_path"
echo "Destination : $destination"
