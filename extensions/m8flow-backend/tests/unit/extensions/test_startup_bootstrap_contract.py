import pytest
from flask import Flask
from pathlib import Path

def test_startup_contract_app_created(m8flow_app):
    app = m8flow_app
    assert app is not None

    from extensions.startup.guard import phase, BootPhase
    assert phase() == BootPhase.APP_CREATED

    from m8flow_backend.canonical_db import get_canonical_db
    db = get_canonical_db()

    flask_app = getattr(app, "app", None)
    assert flask_app is not None

    with flask_app.app_context():
        _ = db.engine

    from extensions.startup.model_identity import assert_model_identity
    assert_model_identity()


def test_no_db_import_before_bootstrap():
    from extensions.startup.guard import import_events

    events = import_events()
    db_events = [e for e in events if e[1] == "spiffworkflow_backend.models.db"]
    assert db_events, (
        "Expected spiff db import to be recorded. "
        "Make sure the orchestrator uses extensions.startup.import_contracts.import_spiff_db()."
    )

    first_phase, _ = db_events[0]
    assert first_phase != "PRE_BOOTSTRAP", f"spiff db imported too early: {first_phase}"


def _count_named(funcs, name: str) -> int:
    return sum(1 for func in funcs if getattr(func, "__name__", "") == name)


def test_create_application_pipeline_order(monkeypatch):
    from extensions.startup import sequence

    calls: list[str] = []
    fake_db = object()
    fake_cnx_app = object()

    def _fake_prepare():
        calls.append("prepare")
        return fake_db, lambda: None

    def _fake_create():
        calls.append("create")
        return fake_cnx_app

    def _fake_configure(cnx_app, db, _upgrade):
        calls.append("configure")
        assert cnx_app is fake_cnx_app
        assert db is fake_db

    def _fake_wrap(cnx_app):
        calls.append("wrap")
        assert cnx_app is fake_cnx_app
        return "wrapped"

    monkeypatch.setattr(sequence, "_prepare_pre_app_boot", _fake_prepare)
    monkeypatch.setattr(sequence, "_create_connexion_app", _fake_create)
    monkeypatch.setattr(sequence, "_configure_created_app", _fake_configure)
    monkeypatch.setattr(sequence, "_wrap_asgi_if_needed", _fake_wrap)

    wrapped = sequence.create_application()
    assert wrapped == "wrapped"
    assert calls == ["prepare", "create", "configure", "wrap"]


def test_wrap_asgi_if_needed_skips_for_testing_env(monkeypatch):
    from extensions.startup import sequence

    app = object()
    monkeypatch.setenv("SPIFFWORKFLOW_BACKEND_ENV", "unit_testing")

    class _ShouldNotWrap:
        def __init__(self, _app):
            raise AssertionError("ASGI wrapper must not run in unit_testing")

    monkeypatch.setattr(sequence, "AsgiTenantContextMiddleware", _ShouldNotWrap)
    assert sequence._wrap_asgi_if_needed(app) is app


def test_wrap_asgi_if_needed_wraps_for_non_testing_env(monkeypatch):
    from extensions.startup import sequence

    app = object()
    monkeypatch.setenv("SPIFFWORKFLOW_BACKEND_ENV", "local_development")

    class _Wrapped:
        def __init__(self, wrapped_app):
            self.wrapped_app = wrapped_app

    monkeypatch.setattr(sequence, "AsgiTenantContextMiddleware", _Wrapped)
    wrapped = sequence._wrap_asgi_if_needed(app)

    assert isinstance(wrapped, _Wrapped)
    assert wrapped.wrapped_app is app


def test_request_hooks_are_idempotent():
    from extensions.startup.flask_hooks import (
        register_request_active_hooks,
        register_request_tenant_context_hooks,
    )

    app = Flask(__name__)

    register_request_active_hooks(app)
    register_request_active_hooks(app)
    register_request_tenant_context_hooks(app)
    register_request_tenant_context_hooks(app)

    before_funcs = app.before_request_funcs.get(None, [])
    teardown_funcs = app.teardown_request_funcs.get(None, [])

    assert _count_named(before_funcs, "_m8flow_mark_request_active") == 1
    assert _count_named(before_funcs, "_m8flow_before_request") == 1
    assert _count_named(teardown_funcs, "_m8flow_unmark_request_active") == 1
    assert _count_named(teardown_funcs, "_m8flow_teardown_request") == 1


def test_import_spiff_db_requires_post_bootstrap():
    from extensions.startup.guard import BootPhase, phase, set_phase
    from extensions.startup.import_contracts import import_spiff_db

    previous_phase = phase()
    try:
        set_phase(BootPhase.PRE_BOOTSTRAP)
        with pytest.raises(RuntimeError, match="import spiffworkflow_backend.models.db"):
            import_spiff_db()
    finally:
        set_phase(previous_phase)


def test_core_post_app_patches_require_app_created():
    from extensions.bootstrap import bootstrap_after_app
    from extensions.startup.guard import BootPhase, phase, set_phase

    previous_phase = phase()
    try:
        set_phase(BootPhase.POST_BOOTSTRAP)
        with pytest.raises(RuntimeError, match="required phase >= BootPhase.APP_CREATED"):
            bootstrap_after_app(object())
    finally:
        set_phase(previous_phase)


def test_extension_post_app_patches_require_app_created():
    from extensions.startup.auth_patches import apply_extension_patches_after_app
    from extensions.startup.guard import BootPhase, phase, set_phase

    previous_phase = phase()
    try:
        set_phase(BootPhase.POST_BOOTSTRAP)
        with pytest.raises(RuntimeError, match="required phase >= BootPhase.APP_CREATED"):
            apply_extension_patches_after_app(object())
    finally:
        set_phase(previous_phase)


def test_patch_registry_covers_all_patch_modules():
    from extensions.startup.patch_registry import registered_patch_modules

    src_root = Path(__file__).resolve().parents[3] / "src" / "m8flow_backend"
    discovered_patch_modules = {
        "m8flow_backend." + ".".join(path.relative_to(src_root).with_suffix("").parts)
        for path in src_root.rglob("*_patch.py")
    }

    missing = discovered_patch_modules - registered_patch_modules()
    assert not missing, (
        "Patch modules must be registered in extensions.startup.patch_registry "
        f"(missing={sorted(missing)})."
    )


def test_patch_registry_app_patch_is_idempotent_per_app(monkeypatch):
    from extensions.startup import patch_registry
    from extensions.startup.guard import BootPhase, phase, set_phase

    calls: list[object] = []

    def _fake_patch(flask_app):
        calls.append(flask_app)

    monkeypatch.setattr(
        patch_registry,
        "_resolve_patch_target",
        lambda _target: (_fake_patch, "tests.fake_module", "fake_patch"),
    )

    spec = patch_registry.PatchSpec(
        target="tests.fake_module:fake_patch",
        minimum_phase=BootPhase.APP_CREATED,
        needs_flask_app=True,
    )

    app_a = Flask("app-a")
    app_b = Flask("app-b")

    previous_phase = phase()
    try:
        set_phase(BootPhase.APP_CREATED)
        assert patch_registry.apply_patch_spec(spec, flask_app=app_a) is True
        assert patch_registry.apply_patch_spec(spec, flask_app=app_a) is False
        assert patch_registry.apply_patch_spec(spec, flask_app=app_b) is True
    finally:
        set_phase(previous_phase)

    assert calls == [app_a, app_b]


def test_patch_registry_optional_import_skips_missing_target_module():
    from extensions.startup import patch_registry
    from extensions.startup.guard import BootPhase, phase, set_phase

    spec = patch_registry.PatchSpec(
        target="m8flow_backend.services.this_module_does_not_exist:apply",
        minimum_phase=BootPhase.APP_CREATED,
        optional_import=True,
    )

    previous_phase = phase()
    try:
        set_phase(BootPhase.APP_CREATED)
        assert patch_registry.apply_patch_spec(spec) is False
    finally:
        set_phase(previous_phase)


def test_patch_registry_optional_import_does_not_hide_transitive_missing_dep(monkeypatch):
    from extensions.startup import patch_registry
    from extensions.startup.guard import BootPhase, phase, set_phase

    monkeypatch.setattr(patch_registry, "_APPLIED_PATCH_TARGETS", set())

    def _raise_transitive_module_not_found(_target: str):
        raise ModuleNotFoundError("No module named 'missing_dependency'", name="missing_dependency")

    monkeypatch.setattr(patch_registry, "_resolve_patch_target", _raise_transitive_module_not_found)

    spec = patch_registry.PatchSpec(
        target="m8flow_backend.services.authentication_service_patch:apply_auth_config_on_demand_patch",
        minimum_phase=BootPhase.APP_CREATED,
        optional_import=True,
    )

    previous_phase = phase()
    try:
        set_phase(BootPhase.APP_CREATED)
        with pytest.raises(ModuleNotFoundError, match="missing_dependency"):
            patch_registry.apply_patch_spec(spec)
    finally:
        set_phase(previous_phase)
