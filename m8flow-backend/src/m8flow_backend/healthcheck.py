"""Container healthcheck for the backend HTTP process."""

from __future__ import annotations

import os
import sys
from http import client

from m8flow_backend.api_versions import api_version_prefix_for_configured_value


def check_backend_health() -> int:
    """Return a healthcheck exit code and print concise failure diagnostics."""
    try:
        version_prefix = api_version_prefix_for_configured_value(
            os.environ.get("M8FLOW_API_VERSION")
        )
    except ValueError as exc:
        print(f"Healthcheck configuration error: {exc}", file=sys.stderr)
        return 2

    try:
        port = int(os.environ.get("M8FLOW_BACKEND_PORT", "6840"))
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        print(
            "Healthcheck configuration error: M8FLOW_BACKEND_PORT must be an "
            "integer between 1 and 65535.",
            file=sys.stderr,
        )
        return 2

    health_path = f"{version_prefix}/healthy"
    connection = client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request("GET", health_path)
        response = connection.getresponse()
        if 200 <= response.status < 300:
            return 0
        print(
            f"Backend health endpoint returned HTTP {response.status}.",
            file=sys.stderr,
        )
        return 1
    except (client.HTTPException, OSError, TimeoutError) as exc:
        print(
            "Backend health request to "
            f"127.0.0.1:{port}{health_path} failed: {type(exc).__name__}.",
            file=sys.stderr,
        )
        return 1
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(check_backend_health())
