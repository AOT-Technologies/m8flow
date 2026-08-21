"""The NATS worker entrypoints named in deploy config must exist and stay in sync.

Three places name a worker script by path — the compose `command`, the consumer image's
Dockerfile (`COPY` + `CMD`), and the wheel's packaged modules — and none of them is checked
by an import, a type checker, or a lint. Renaming a worker (as `consumer.py` ->
`trigger_event_consumer.py` did) therefore fails at container start rather than in CI, and
only for whichever of the three was missed.

The compose service also idles instead of exiting when `M8FLOW_NATS_ENABLED` is not "true",
so a dangling path can hide as "the consumer just isn't running", which is indistinguishable
from the intended disabled state.

These are static consistency checks; they deliberately do not start a container.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

repo_root = Path(__file__).resolve().parents[4]
consumer_dir = repo_root / "m8flow-nats-consumer"
compose_path = repo_root / "docker" / "m8flow-docker-compose.yml"
dockerfile_path = consumer_dir / "Dockerfile"
pyproject_path = consumer_dir / "pyproject.toml"

# Every worker script the deployment is expected to be able to launch.
WORKER_SCRIPTS = ["trigger_event_consumer.py", "notification_worker.py"]


@pytest.mark.parametrize("script", WORKER_SCRIPTS)
def test_the_worker_script_exists(script: str) -> None:
    assert (consumer_dir / script).is_file(), f"{script} is named in deploy config but absent"


@pytest.mark.parametrize("script", WORKER_SCRIPTS)
def test_compose_launches_a_script_that_exists(script: str) -> None:
    """Each `python .../<script>` in compose must resolve to a real file."""
    compose = compose_path.read_text(encoding="utf-8")
    launched = set(re.findall(r"python\s+(m8flow-nats-consumer/[\w./-]+\.py)", compose))
    assert launched, "no consumer entrypoint found in compose; did the command shape change?"

    missing = [path for path in launched if not (repo_root / path).is_file()]
    assert not missing, f"compose launches non-existent script(s): {missing}"


def test_the_dockerfile_copies_what_it_runs() -> None:
    """A CMD naming a file the image never COPYed fails only at container start."""
    dockerfile = dockerfile_path.read_text(encoding="utf-8")

    cmd = re.search(r'CMD\s+\["python",\s*"([^"]+)"\]', dockerfile)
    assert cmd, "consumer Dockerfile has no recognisable python CMD"
    entrypoint = cmd.group(1)

    copied = set(re.findall(r"^COPY\s+([\w./-]+\.py)\s", dockerfile, flags=re.MULTILINE))
    assert entrypoint in copied, f"CMD runs {entrypoint!r}, which is never COPYed ({sorted(copied)})"
    assert (consumer_dir / entrypoint).is_file()


def test_the_wheel_packages_the_entrypoint() -> None:
    """`packages` still pointing at the old name yields an image missing the module."""
    pyproject = pyproject_path.read_text(encoding="utf-8")
    packaged = set(re.findall(r'"([\w./-]+\.py)"', pyproject))
    assert packaged, "no packaged modules found in consumer pyproject.toml"

    missing = [name for name in packaged if not (consumer_dir / name).is_file()]
    assert not missing, f"pyproject packages non-existent module(s): {missing}"


def test_no_stale_reference_to_the_pre_rename_consumer() -> None:
    """`consumer.py` was renamed to `trigger_event_consumer.py`; nothing may still name it."""
    stale = []
    for path in (compose_path, dockerfile_path, pyproject_path):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"(?<![\w-])consumer\.py", line):
                stale.append(f"{path.relative_to(repo_root)}:{line_number}")
    assert not stale, f"stale reference(s) to the pre-rename consumer.py: {stale}"


def test_the_consumer_still_owns_the_broker_metrics_loop() -> None:
    """Docs and the Grafana dashboards depend on this worker publishing broker metrics.

    Asserted structurally (defined *and* scheduled) because a rename that dropped the task
    would leave the dashboards silently empty rather than failing anything.
    """
    source = (consumer_dir / "trigger_event_consumer.py").read_text(encoding="utf-8")
    assert "async def broker_metrics_loop" in source
    assert "create_task(broker_metrics_loop())" in source


def test_the_consumer_still_handles_termination_signals() -> None:
    """Without these, `docker compose down` kills the worker mid-message instead of draining."""
    source = (consumer_dir / "trigger_event_consumer.py").read_text(encoding="utf-8")
    for signal_name in ("SIGINT", "SIGTERM"):
        assert f"signal.{signal_name}" in source, f"{signal_name} handler is gone"
