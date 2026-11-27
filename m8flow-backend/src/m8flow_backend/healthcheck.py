"""Container healthcheck for the backend HTTP process."""

from __future__ import annotations

import os
import sys
from urllib import error, request

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

    port = os.environ.get("M8FLOW_BACKEND_PORT", "6840")
    health_url = f"http://127.0.0.1:{port}{version_prefix}/healthy"
    try:
        with request.urlopen(health_url, timeout=5) as response:
            if 200 <= response.status < 300:
                return 0
            print(
                f"Backend health endpoint returned HTTP {response.status}.",
                file=sys.stderr,
            )
            return 1
    except error.HTTPError as exc:
        print(
            f"Backend health endpoint {health_url} returned HTTP {exc.code}.",
            file=sys.stderr,
        )
        return 1
    except (error.URLError, TimeoutError, OSError) as exc:
        print(
            f"Backend health request to {health_url} failed: {type(exc).__name__}.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(check_backend_health())
