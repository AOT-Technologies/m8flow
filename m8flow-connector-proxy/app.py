import logging
import os

from spiffworkflow_proxy.blueprint import proxy_blueprint
from flask import Flask, g, request

from m8flow_connector_context import (
    M8flowConnectorLogFilter,
    infer_connector_from_path,
)

app = Flask(__name__)
app.config.from_pyfile("config.py", silent=True)

if app.config.get("ENV", "development") != "production":
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

app.register_blueprint(proxy_blueprint)


@app.before_request
def _m8flow_set_connector_log_context() -> None:
    g.m8flow_connector = infer_connector_from_path(request.path or "")


from otel_setup import setup_otel

setup_otel(app)

# Enrich all log lines with a stable search token for Loki (OTLP + stdout).
_log_filter = M8flowConnectorLogFilter()
_root = logging.getLogger()
_root.addFilter(_log_filter)
_conn_fmt = logging.Formatter(
    "%(asctime)s %(levelname)s [%(name)s] m8flow_connector=%(m8flow_connector)s %(message)s"
)
for _h in _root.handlers:
    _h.setFormatter(_conn_fmt)
logging.getLogger("werkzeug").addFilter(_log_filter)

if __name__ == "__main__":
    app.run(host="localhost", port=7004)
