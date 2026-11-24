from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from m8flow_backend.catalog import default_bpmn_xml, versions
from m8flow_backend.identity import ensure_tenant
from m8flow_backend.models.process_model_version import (
    ProcessInstanceCalledReleases,
    ProcessModelRelease,
    ProcessModelState,
)


def test_catalog_migration_rolls_back_and_retries_with_postgres_rls(admin_engine, migrated_database, monkeypatch, tmp_path):
    runtime_url = sa.engine.make_url(migrated_database.runtime_uri)
    schema = f"catalog_import_{uuid4().hex}"
    quote = admin_engine.dialect.identifier_preparer.quote
    with admin_engine.begin() as connection:
        connection.execute(sa.text(f"CREATE SCHEMA {quote(schema)} AUTHORIZATION {quote(runtime_url.username)}"))

    engine = sa.create_engine(runtime_url.update_query_dict({"options": f"-c search_path={schema}"}))
    monkeypatch.setenv("M8FLOW_BACKEND_DATABASE_URI", engine.url.render_as_string(hide_password=False))
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "migrations"))
    previous = "fbcad9e02138"
    tenants = ("m8flow", "second-tenant")
    model_id = "test/review"
    tables = (ProcessInstanceCalledReleases.__table__, ProcessModelRelease.__table__, ProcessModelState.__table__)
    stamp = sa.text("SELECT version_num FROM alembic_version_m8flow")
    set_tenant = sa.text("SELECT set_config('app.current_tenant', :tenant, true)")
    current_tenant = sa.text("SELECT current_setting('app.current_tenant', true)")

    try:
        command.upgrade(cfg, previous)
        with engine.begin() as connection:
            assert connection.execute(sa.text(
                "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
            )).one() == (False, False)
            # The squashed root builds from current ORM metadata. Start with
            # the schema deployed by the predecessor before version tables existed.
            for table in tables:
                table.drop(connection, checkfirst=True)
        with Session(engine) as session, session.begin():
            for tenant_id in tenants:
                ensure_tenant(session, tenant_id=tenant_id)
                folder = tmp_path / tenant_id / model_id
                folder.mkdir(parents=True)
                (folder / "review.bpmn").write_text(default_bpmn_xml(process_id="review"), encoding="utf-8")

        import_legacy = versions.import_legacy

        def fail_second_import(session, tenant_id, identifier):
            assert session.scalar(current_tenant) == tenant_id
            model = import_legacy(session, tenant_id, identifier)
            if tenant_id == tenants[-1]:
                assert model is not None
                raise ValueError("injected second tenant failure")
            return model

        def clear_tenant_at_session_start(_session, _transaction, connection):
            assert connection.scalar(current_tenant) == tenants[0]
            connection.execute(set_tenant, {"tenant": ""})

        sa.event.listen(Session, "after_begin", clear_tenant_at_session_start)
        try:
            with pytest.raises(RuntimeError, match="while preparing the tenant import") as exc:
                command.upgrade(cfg, "head")
            assert isinstance(exc.value.__cause__, RuntimeError)
            assert "PostgreSQL tenant context does not match" in str(exc.value.__cause__)
        finally:
            sa.event.remove(Session, "after_begin", clear_tenant_at_session_start)

        with monkeypatch.context() as patch:
            patch.setattr(versions, "import_legacy", fail_second_import)
            with pytest.raises(RuntimeError, match="tenant 'second-tenant' while importing model 'test/review'") as exc:
                command.upgrade(cfg, "head")
        assert isinstance(exc.value.__cause__, ValueError)
        with engine.connect() as connection:
            assert connection.scalar(stamp) == previous
            assert {table.name for table in tables}.isdisjoint(sa.inspect(connection).get_table_names())

        command.upgrade(cfg, "head")
        with Session(engine) as session, session.begin():
            assert session.scalar(stamp) == "d8e9f0a1b2c3"
            assert session.scalars(sa.select(ProcessModelState)).all() == []
            assert session.scalars(sa.select(ProcessModelRelease)).all() == []
            for tenant_id in tenants:
                session.execute(set_tenant, {"tenant": tenant_id})
                model, = session.scalars(sa.select(ProcessModelState))
                release, = session.scalars(sa.select(ProcessModelRelease))
                assert model.m8f_tenant_id == release.m8f_tenant_id == tenant_id
                assert model.model_id == release.model_id == model_id
                assert model.status == "published"
                assert model.latest_version == release.version == 1
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(sa.schema.DropSchema(schema, cascade=True))
