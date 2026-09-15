from __future__ import annotations

import copy
import logging.config
from pathlib import Path

import yaml

_LOG_CONFIG_PATH = Path(__file__).resolve().parents[5] / "uvicorn-log.yaml"


def _load_config() -> dict:
    return yaml.safe_load(_LOG_CONFIG_PATH.read_text(encoding="utf-8"))


def test_uvicorn_log_yaml_exists_and_parses():
    assert _LOG_CONFIG_PATH.is_file(), f"expected {_LOG_CONFIG_PATH} to exist"
    config = _load_config()
    assert config["handlers"]["console"]["formatter"] == "default"
    assert set(config["handlers"]["console"]["filters"]) == {"tenant_ctx", "request_ctx", "otel_trace_ctx"}


def test_uvicorn_log_yaml_custom_object_paths_are_importable():
    """Every `()`-style factory path in uvicorn-log.yaml must resolve, or
    the real server would fail to boot with only a stderr traceback."""
    config = _load_config()
    for name, spec in {**config["filters"], **config["formatters"]}.items():
        dotted_path = spec["()"]
        module_name, attr = dotted_path.rsplit(".", 1)
        module = __import__(module_name, fromlist=[attr])
        factory = getattr(module, attr)
        instance = factory()
        assert instance is not None, f"{name} ({dotted_path}) factory returned None"


def test_uvicorn_log_yaml_applies_cleanly_via_dictconfig():
    """Smoke-test the full dictConfig apply, then restore prior logging state
    so this test doesn't leak handlers into the rest of the suite."""
    previous_root_handlers = list(logging.root.handlers)
    previous_root_level = logging.root.level
    config = copy.deepcopy(_load_config())
    try:
        logging.config.dictConfig(config)
        logging.getLogger("m8flow_backend.test.uvicorn_log_config").info("uvicorn-log.yaml smoke test")
    finally:
        logging.root.handlers = previous_root_handlers
        logging.root.setLevel(previous_root_level)
