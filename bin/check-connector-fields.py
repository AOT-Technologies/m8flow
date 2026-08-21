#!/usr/bin/env python3
"""Check every connector definition's field names against the live proxy.

The connector proxy builds each command as ``command(**params)``, so a field name
that the connector does not declare is silently never sent -- the profile value
just does not arrive, and the failure surfaces as a confusing auth or validation
error from the remote system rather than as a misconfiguration.

This reads ``GET {proxy}/v1/commands`` and reports, per connector:

  MISSING   a definition field no operation of that connector accepts
  UNUSED    an operation parameter no profile can supply (informational)

Run it after bumping the pinned m8flow-connectors version, which is when a
rename would otherwise slip through unnoticed.

    python bin/check-connector-fields.py
    python bin/check-connector-fields.py --proxy-url http://localhost:6844

Exits non-zero when any MISSING field is found.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "m8flow-backend" / "src"))

DEFAULT_PROXY_URL = os.environ.get(
    "M8FLOW_BACKEND_CONNECTOR_PROXY_URL", "http://localhost:6844"
)


def fetch_commands(proxy_url: str) -> list[dict]:
    url = f"{proxy_url.rstrip('/')}/v1/commands"
    try:
        with urllib.request.urlopen(url, timeout=15) as response:  # noqa: S310
            return json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        print(f"error: could not read {url}: {error}", file=sys.stderr)
        print(
            "hint: start the proxy (docker compose up m8flow-connector-proxy) "
            "or pass --proxy-url.",
            file=sys.stderr,
        )
        raise SystemExit(2) from error


def parameters_by_connector(commands: list[dict]) -> dict[str, set[str]]:
    """Union of parameter names across each connector's operations."""
    result: dict[str, set[str]] = defaultdict(set)
    for command in commands:
        operator_id = command.get("id") or ""
        if "/" not in operator_id:
            continue
        connector_type = operator_id.split("/", 1)[0]
        for parameter in command.get("parameters", []):
            name = parameter.get("id")
            if name:
                result[connector_type].add(name)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proxy-url", default=DEFAULT_PROXY_URL)
    parser.add_argument(
        "--show-unused",
        action="store_true",
        help="also list operation parameters no profile field supplies",
    )
    args = parser.parse_args()

    from m8flow_backend.connectors.registry import all_connectors

    live = parameters_by_connector(fetch_commands(args.proxy_url))
    if not live:
        print("error: the proxy returned no commands.", file=sys.stderr)
        return 2

    failures = 0
    for definition in all_connectors():
        connector_type = definition.connector_type
        accepted = live.get(connector_type)

        if accepted is None:
            print(f"{connector_type}: SKIP (not offered by this proxy)")
            continue

        declared = {definition.wire_name(name) for name in definition.model_fields}
        missing = sorted(declared - accepted)
        unused = sorted(accepted - declared)

        if missing:
            failures += len(missing)
            print(f"{connector_type}: MISSING {missing}")
            print(
                f"  the connector accepts {sorted(accepted)}; these names would "
                f"never be sent."
            )
        else:
            print(f"{connector_type}: OK ({len(declared)} fields)")

        if unused and args.show_unused:
            print(f"  UNUSED (no profile field supplies these): {unused}")

    if failures:
        print(f"\nFAIL: {failures} field name(s) the connectors do not accept.")
        return 1

    print("\nPASS: every definition field is a real connector parameter.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
