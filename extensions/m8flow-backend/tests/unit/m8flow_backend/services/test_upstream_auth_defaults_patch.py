from __future__ import annotations

from flask import Flask

from m8flow_backend.services import upstream_auth_defaults_patch


def test_apply_seeds_env_defaults_without_importing_upstream(monkeypatch) -> None:
    monkeypatch.setattr(upstream_auth_defaults_patch, "_PATCHED", False)
    monkeypatch.delenv("SPIFFWORKFLOW_BACKEND_OPEN_ID_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPIFFWORKFLOW_BACKEND_OPEN_ID_SERVER_URL", raising=False)
    for key in list(upstream_auth_defaults_patch.os.environ):
        if key == "SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS" or key.startswith("SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS__"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("KEYCLOAK_HOSTNAME", "http://public-keycloak:7002")
    monkeypatch.setenv("KEYCLOAK_URL", "http://internal-keycloak:7002")

    upstream_auth_defaults_patch.apply()

    assert upstream_auth_defaults_patch.os.environ["SPIFFWORKFLOW_BACKEND_OPEN_ID_CLIENT_ID"] == "m8flow-backend"
    assert upstream_auth_defaults_patch.os.environ["SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS__0__identifier"] == "default"
    assert upstream_auth_defaults_patch.os.environ["SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS__0__label"] == "M8Flow Realm"
    assert upstream_auth_defaults_patch.os.environ["SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS__0__uri"] == "http://public-keycloak:7002/realms/m8flow"
    assert (
        upstream_auth_defaults_patch.os.environ["SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS__0__internal_uri"]
        == "http://internal-keycloak:7002/realms/m8flow"
    )
    assert upstream_auth_defaults_patch.os.environ["SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS__0__client_id"] == "m8flow-backend"


def test_apply_runtime_rewrites_upstream_defaults_on_flask_config() -> None:
    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_OPEN_ID_CLIENT_ID"] = "spiffworkflow-backend"
    app.config["SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS"] = [
        {
            "identifier": "default",
            "label": "Default",
            "uri": "http://localhost:7002/realms/spiffworkflow-local",
            "internal_uri": "http://localhost:7002/realms/spiffworkflow-local",
            "client_id": "spiffworkflow-backend",
            "client_secret": "JXeQExm0JhQPLumgHtIIqf52bDalHz0q",
        }
    ]

    upstream_auth_defaults_patch.apply_runtime(app)

    assert app.config["SPIFFWORKFLOW_BACKEND_OPEN_ID_CLIENT_ID"] == "m8flow-backend"
    assert app.config["SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS"][0]["uri"] == "http://localhost:7002/realms/m8flow"
    assert app.config["SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS"][0]["internal_uri"] == "http://localhost:7002/realms/m8flow"
    assert app.config["SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS"][0]["client_id"] == "m8flow-backend"


def test_apply_runtime_fills_missing_auth_config_labels() -> None:
    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS"] = [
        {
            "identifier": "master",
            "uri": "http://localhost:7002/realms/master",
            "client_id": "m8flow-backend",
        },
        {
            "identifier": "m8flow",
            "uri": "http://localhost:7002/realms/m8flow",
            "client_id": "m8flow-backend",
        },
        {
            "uri": "http://localhost:7002/realms/unknown",
            "client_id": "m8flow-backend",
        },
    ]

    upstream_auth_defaults_patch.apply_runtime(app)

    assert app.config["SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS"][0]["label"] == "Master"
    assert app.config["SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS"][1]["label"] == "M8Flow Realm"
    assert app.config["SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS"][2]["label"] == "Default"


def test_apply_runtime_leaves_custom_config_unchanged() -> None:
    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_OPEN_ID_CLIENT_ID"] = "custom-client"
    app.config["SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS"] = [
        {
            "identifier": "custom",
            "label": "Custom",
            "uri": "http://custom/realm",
            "internal_uri": "http://custom/internal",
            "client_id": "custom-client",
            "client_secret": "custom-secret",
        }
    ]

    upstream_auth_defaults_patch.apply_runtime(app)

    assert app.config["SPIFFWORKFLOW_BACKEND_OPEN_ID_CLIENT_ID"] == "custom-client"
    assert app.config["SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS"][0]["uri"] == "http://custom/realm"
    assert app.config["SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS"][0]["client_id"] == "custom-client"


def test_apply_runtime_normalizes_uppercase_auth_config_keys() -> None:
    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS"] = [
        {
            "IDENTIFIER": "m8flow",
            "LABEL": "M8Flow Realm",
            "URI": "http://localhost:7002/realms/m8flow",
            "INTERNAL_URI": "http://localhost:7002/realms/m8flow",
            "CLIENT_ID": "m8flow-backend",
            "CLIENT_SECRET": "secret",
            "ADDITIONAL_VALID_CLIENT_IDS": "admin-cli",
        }
    ]

    upstream_auth_defaults_patch.apply_runtime(app)

    auth_config = app.config["SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS"][0]
    assert auth_config["identifier"] == "m8flow"
    assert auth_config["label"] == "M8Flow Realm"
    assert auth_config["uri"] == "http://localhost:7002/realms/m8flow"
    assert auth_config["internal_uri"] == "http://localhost:7002/realms/m8flow"
    assert auth_config["client_id"] == "m8flow-backend"
    assert auth_config["client_secret"] == "secret"
    assert auth_config["additional_valid_client_ids"] == "admin-cli"
    assert "IDENTIFIER" not in auth_config
