# extensions/startup/config.py
import os
import logging

logger = logging.getLogger(__name__)

def _env_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}

def configure_sql_echo(flask_app, db) -> None:
    if not _env_truthy(os.environ.get("M8FLOW_SQLALCHEMY_ECHO")):
        return
    flask_app.config["SQLALCHEMY_ECHO"] = True
    try:
        with flask_app.app_context():
            db.engine.echo = True
    except Exception:
        pass

def configure_templates_dir(flask_app) -> None:
    m8flow_templates_dir = os.environ.get("M8FLOW_TEMPLATES_STORAGE_DIR")
    if m8flow_templates_dir:
        flask_app.config["M8FLOW_TEMPLATES_STORAGE_DIR"] = m8flow_templates_dir
        logger.info("M8FLOW_TEMPLATES_STORAGE_DIR configured: %s", m8flow_templates_dir)

def configure_permissions_yml(flask_app) -> None:
    import m8flow_backend
    yml_path = os.path.join(os.path.dirname(m8flow_backend.__file__), "config", "permissions", "m8flow.yml")
    if os.path.isfile(yml_path):
        abs_path = os.path.abspath(yml_path)
        flask_app.config["SPIFFWORKFLOW_BACKEND_PERMISSIONS_FILE_ABSOLUTE_PATH"] = abs_path
        logger.info("M8Flow: using permissions file %s", abs_path)