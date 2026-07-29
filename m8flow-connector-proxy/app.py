import os
import time

from spiffworkflow_proxy.blueprint import proxy_blueprint
from flask import Flask, g, has_app_context, request

app = Flask(__name__)
app.config.from_pyfile("config.py", silent=True)

if app.config.get("ENV", "development") != "production":
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

record_connector_call = None
_telemetry_set_tenant = None


def _resolve_connector_tenant_id() -> str | None:
    # The OTel log processor/filter can fire outside any Flask app or request
    # context (e.g. startup-time logging) — touching `g` there raises
    # RuntimeError, which getattr(..., default) does NOT swallow (it only
    # catches AttributeError), so this must check has_app_context() first.
    if not has_app_context():
        return None
    return getattr(g, "m8flow_tenant_id", None)


try:
    from m8flow_telemetry.bootstrap import instrument_flask_app, setup
    from m8flow_telemetry.context import set_tenant_id as _telemetry_set_tenant
    from m8flow_telemetry.metrics import record_connector_call as _record_connector_call

    setup("m8flow-connector-proxy", tenant_resolver=_resolve_connector_tenant_id)
    instrument_flask_app(app)
    record_connector_call = _record_connector_call
except ImportError:  # pragma: no cover
    pass


@app.before_request
def _capture_connector_tenant() -> None:
    g._connector_started_at = time.perf_counter()
    tenant_header = request.headers.get("X-M8Flow-Tenant-Id") or request.headers.get("m8flow_tenant_id")
    if tenant_header:
        g.m8flow_tenant_id = tenant_header.strip()
        if _telemetry_set_tenant is not None:
            _telemetry_set_tenant(g.m8flow_tenant_id)


@app.after_request
def _observe_connector_call(response):
    if record_connector_call is None:
        return response
    if request.path in {"/liveness", "/health"}:
        return response
    connector = request.view_args.get("connector_id") if request.view_args else request.path
    started = getattr(g, "_connector_started_at", None)
    duration_ms = (time.perf_counter() - started) * 1000 if started else 0.0
    record_connector_call(
        getattr(g, "m8flow_tenant_id", None),
        connector=str(connector or "unknown"),
        duration_ms=duration_ms,
        failed=response.status_code >= 500,
    )
    return response


app.register_blueprint(proxy_blueprint)

if __name__ == "__main__":
    app.run(host="localhost", port=7004)
