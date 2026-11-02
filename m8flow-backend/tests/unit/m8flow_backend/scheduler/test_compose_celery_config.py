from __future__ import annotations

from pathlib import Path

import yaml


def test_compose_configures_beat_as_the_only_timer_polling_owner():
    compose_path = Path(__file__).resolve().parents[5] / "docker" / "m8flow-docker-compose.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    services = compose["services"]

    api_environment = services["m8flow-backend"]["environment"]
    worker_environment = services["m8flow-celery-worker"]["environment"]
    beat_service = services["m8flow-celery-beat"]
    beat_environment = beat_service["environment"]

    assert api_environment["M8FLOW_BACKEND_RUN_BACKGROUND_SCHEDULER_IN_CREATE_APP"] == "false"
    assert worker_environment["M8FLOW_BACKEND_RUN_BACKGROUND_SCHEDULER_IN_CREATE_APP"] == "false"
    assert beat_environment["M8FLOW_BACKEND_RUN_BACKGROUND_SCHEDULER_IN_CREATE_APP"] == "false"
    assert beat_service["depends_on"]["redis"]["condition"] == "service_healthy"
    assert "m8flow-backend" not in beat_service["depends_on"]
    assert [name for name in services if "celery-beat" in name] == ["m8flow-celery-beat"]
