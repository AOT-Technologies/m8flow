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

    # API, worker, and Beat must publish/consume against the same Compose Redis.
    for key in ("M8FLOW_BACKEND_CELERY_BROKER_URL", "M8FLOW_BACKEND_CELERY_RESULT_BACKEND"):
        assert api_environment[key] == worker_environment[key] == beat_environment[key]
        assert "redis:6379/0" in api_environment[key]
    assert "celery" in beat_service["command"]
    assert "beat" in beat_service["command"]
    assert "run_m8flow_celery_worker.sh" in services["m8flow-celery-worker"]["command"]
