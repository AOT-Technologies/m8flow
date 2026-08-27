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


def configure_vault(flask_app) -> None:
    from m8flow_backend.services.vault_client import VaultClient, VaultSettings
    from m8flow_backend.config import vault_enabled

    settings = VaultSettings.from_env()
    enabled = vault_enabled()

    flask_app.config["M8FLOW_VAULT_ENABLED"] = enabled
    flask_app.config["M8FLOW_VAULT_ADDR"] = settings.addr
    flask_app.config["M8FLOW_VAULT_NAMESPACE"] = settings.namespace
    flask_app.config["M8FLOW_VAULT_MOUNT_POINT"] = settings.mount_point
    flask_app.config["M8FLOW_VAULT_SECRET_PATH_PREFIX"] = settings.secret_path_prefix
    flask_app.config["M8FLOW_VAULT_TIMEOUT_SECONDS"] = settings.timeout_seconds
    flask_app.config["M8FLOW_VAULT_AVAILABLE"] = False
    flask_app.config["M8FLOW_SECRET_BACKEND_KIND"] = "legacy"

    if not enabled:
        return

    if not settings.is_configured:
        raise RuntimeError(
            "Vault mode is enabled, but Vault is not fully configured. "
            "Set M8FLOW_VAULT_ADDR and either M8FLOW_VAULT_TOKEN or both "
            "M8FLOW_VAULT_ROLE_ID and M8FLOW_VAULT_SECRET_ID."
        )

    client = VaultClient(settings=settings)
    client.assert_startup_ready()
    flask_app.config["M8FLOW_VAULT_AVAILABLE"] = True
    flask_app.config["M8FLOW_SECRET_BACKEND_KIND"] = "vault"

    logger.info(
        "Vault integration is enabled at %s (mount=%s, prefix=%s, namespace=%s, auth=%s)",
        settings.addr,
        settings.mount_point,
        settings.secret_path_prefix,
        settings.namespace or "-",
        settings.auth_method or "-",
    )
