import celery


def _reset_patch_state(patch_module):
    patch_module._PATCHED = False
    patch_module._ORIGINAL_SEND_TASK = None


def test_send_task_includes_tenant_header(monkeypatch):
    from m8flow_backend.services import celery_tenant_context_patch as patch_module

    _reset_patch_state(patch_module)

    captured: dict = {}

    def _fake_send_task(self, name, args=None, kwargs=None, **options):
        captured["name"] = name
        captured["options"] = options
        return "ok"

    monkeypatch.setattr(celery.Celery, "send_task", _fake_send_task)
    monkeypatch.setattr(patch_module, "get_tenant_id", lambda warn_on_default=False: "tenant-a")

    patch_module.apply()

    app = celery.Celery("test-celery")
    result = app.send_task("test.task")

    assert result == "ok"
    assert captured["name"] == "test.task"
    assert captured["options"]["headers"][patch_module.TENANT_HEADER_NAME] == "tenant-a"


def test_send_task_skips_tenant_header_when_unavailable(monkeypatch):
    from m8flow_backend.services import celery_tenant_context_patch as patch_module

    _reset_patch_state(patch_module)

    captured: dict = {}

    def _fake_send_task(self, name, args=None, kwargs=None, **options):
        captured["name"] = name
        captured["options"] = options
        return "ok"

    monkeypatch.setattr(celery.Celery, "send_task", _fake_send_task)

    def _raise_missing_tenant(*_args, **_kwargs):
        raise RuntimeError("missing tenant")

    monkeypatch.setattr(patch_module, "get_tenant_id", _raise_missing_tenant)

    patch_module.apply()

    app = celery.Celery("test-celery")
    result = app.send_task("test.task")

    assert result == "ok"
    assert captured["name"] == "test.task"
    assert "headers" not in captured["options"]

