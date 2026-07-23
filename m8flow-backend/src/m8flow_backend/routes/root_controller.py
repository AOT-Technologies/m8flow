# m8flow-backend/src/m8flow_backend/routes/root_controller.py
"""Public root endpoint (M8F-409).

Unauthenticated requests to the backend root used to hit tenant resolution and
fail with a confusing ``tenant_required`` error. This controller gives the
backend a friendly front door instead:

- Browsers get a small self-contained HTML page showing live backend health
  (fetched client-side from the public ping endpoint) and a button to Swagger UI.
- API clients (``curl``, scripts) get a JSON payload with discoverable links.

The view is intentionally public: it exposes no tenant data, and it is marked
``_m8flow_sets_tenant_context`` so the global tenant resolver skips it, plus it
is listed in ``M8FLOW_AUTH_EXCLUSION_ADDITIONS`` so upstream auth skips it.
"""
from __future__ import annotations

import json

from flask import Response, current_app, request

_API_PATH_PREFIX_CONFIG_KEY = "SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX"
_DEFAULT_API_PATH_PREFIX = "/v1.0"

_LANDING_PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>M8Flow Backend</title>
<style>
  body {{
    margin: 0;
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    background: #f4f6f8;
    color: #1f2933;
    display: flex;
    min-height: 100vh;
    align-items: center;
    justify-content: center;
  }}
  .card {{
    background: #fff;
    border: 1px solid #e0e5ea;
    border-radius: 12px;
    box-shadow: 0 2px 12px rgba(31, 41, 51, 0.08);
    max-width: 30rem;
    width: calc(100% - 3rem);
    padding: 2rem;
    text-align: center;
  }}
  h1 {{ font-size: 1.4rem; margin: 0 0 0.5rem; }}
  p {{ color: #52606d; margin: 0.25rem 0 1.25rem; }}
  .status {{
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    border-radius: 999px;
    padding: 0.4rem 1rem;
    font-weight: 600;
    margin-bottom: 1.5rem;
    background: #eef1f4;
    color: #52606d;
  }}
  .status[data-state="up"] {{ background: #e3f6e8; color: #1c7c3c; }}
  .status[data-state="down"] {{ background: #fdecea; color: #b3261e; }}
  .dot {{ width: 0.6rem; height: 0.6rem; border-radius: 50%; background: currentColor; }}
  a.button {{
    display: inline-block;
    background: #1d4ed8;
    color: #fff;
    text-decoration: none;
    font-weight: 600;
    border-radius: 8px;
    padding: 0.65rem 1.4rem;
  }}
  a.button:hover {{ background: #1e40af; }}
  .links {{ margin-top: 1.25rem; font-size: 0.85rem; }}
  .links a {{ color: #1d4ed8; text-decoration: none; margin: 0 0.5rem; }}
</style>
</head>
<body>
  <main class="card">
    <h1>M8Flow Backend</h1>
    <p>Workflow engine API server</p>
    <div id="status" class="status" data-state="checking">
      <span class="dot"></span><span id="status-text">Checking health&hellip;</span>
    </div>
    <div>
      <a class="button" href="{swagger_ui_url}">Redirect to Swagger UI</a>
    </div>
    <div class="links">
      <a href="{ping_url}">Health check</a>
    </div>
  </main>
  <script>
    (function () {{
      var badge = document.getElementById("status");
      var text = document.getElementById("status-text");
      fetch("{ping_url}", {{ cache: "no-store" }})
        .then(function (response) {{
          if (!response.ok) {{ throw new Error("status " + response.status); }}
          return response.json();
        }})
        .then(function (body) {{
          var healthy = body && (body.ok === true || body.healthy === true || body.status === "ok");
          badge.dataset.state = healthy ? "up" : "down";
          text.textContent = healthy ? "Backend is healthy" : "Backend reported a problem";
        }})
        .catch(function () {{
          badge.dataset.state = "down";
          text.textContent = "Backend health check failed";
        }});
    }})();
  </script>
</body>
</html>
"""


def _api_path_prefix() -> str:
    try:
        prefix = current_app.config.get(_API_PATH_PREFIX_CONFIG_KEY) or _DEFAULT_API_PATH_PREFIX
    except Exception:
        prefix = _DEFAULT_API_PATH_PREFIX
    prefix = prefix.rstrip("/")
    return prefix or _DEFAULT_API_PATH_PREFIX


def _request_prefers_html() -> bool:
    best = request.accept_mimetypes.best_match(["text/html", "application/json"])
    return best == "text/html" and request.accept_mimetypes[best] > request.accept_mimetypes["application/json"]


def root() -> Response:
    """Public landing endpoint for the backend root path."""
    api_prefix = _api_path_prefix()
    swagger_ui_url = f"{api_prefix}/ui/"
    ping_url = f"{api_prefix}/ping"
    status_url = f"{api_prefix}/status"

    if _request_prefers_html():
        html = _LANDING_PAGE_TEMPLATE.format(
            swagger_ui_url=swagger_ui_url,
            ping_url=ping_url,
        )
        return Response(html, status=200, mimetype="text/html")

    payload = {
        "name": "m8flow-backend",
        "message": "M8Flow backend API is running.",
        "docs": swagger_ui_url,
        "health": ping_url,
        "status": status_url,
    }
    return Response(json.dumps(payload), status=200, mimetype="application/json")


# The root endpoint is public and global; the tenant resolver must not demand a
# tenant for it (see m8flow_backend.startup.tenant_resolution).
root._m8flow_sets_tenant_context = True  # type: ignore[attr-defined]
