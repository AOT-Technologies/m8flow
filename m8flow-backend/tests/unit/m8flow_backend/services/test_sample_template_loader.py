from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace

from m8flow_backend.services import sample_template_loader


def test_load_sample_templates_skips_when_template_table_missing(monkeypatch) -> None:
    warnings: list[str] = []
    isdir_called = False

    class FakeInspector:
        def has_table(self, table_name: str) -> bool:
            assert table_name == sample_template_loader.TemplateModel.__tablename__
            return False

    def fake_inspect(engine):
        return FakeInspector()

    def fake_isdir(path: str) -> bool:
        nonlocal isdir_called
        isdir_called = True
        raise AssertionError("os.path.isdir should not be called when the template table is missing")

    class FakeApp:
        @staticmethod
        def app_context():
            return nullcontext()

    monkeypatch.setenv("M8FLOW_LOAD_SAMPLE_TEMPLATES", "1")
    monkeypatch.setattr(sample_template_loader, "inspect", fake_inspect)
    monkeypatch.setattr(sample_template_loader, "db", SimpleNamespace(engine=object(), session=SimpleNamespace()))
    monkeypatch.setattr(sample_template_loader, "_SAMPLE_TEMPLATES_DIR", "/tmp/unused")
    monkeypatch.setattr(sample_template_loader.os.path, "isdir", fake_isdir)
    monkeypatch.setattr(
        sample_template_loader.logger,
        "warning",
        lambda msg, *args: warnings.append(msg % args if args else msg),
    )
    monkeypatch.setattr(
        sample_template_loader.logger,
        "exception",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("logger.exception should not be called")),
    )

    sample_template_loader.load_sample_templates(FakeApp())

    assert isdir_called is False
    assert warnings == [
        "Skipping sample template loading because table m8flow_templates does not exist yet; run M8FLOW_BACKEND_UPGRADE_DB=1 or apply migrations first."
    ]
