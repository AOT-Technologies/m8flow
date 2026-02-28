# extensions/startup/model_identity.py
def assert_model_identity() -> None:
    from spiffworkflow_backend.models.db import db, SpiffworkflowBaseDBModel
    from m8flow_backend.models.m8flow_tenant import M8flowTenantModel

    assert hasattr(M8flowTenantModel, "__table__"), (
        "M8flowTenantModel is not mapped yet (no __table__). "
        "Likely imported before final db/base established."
    )

    model_md = M8flowTenantModel.__table__.metadata
    db_md = db.metadata
    assert model_md is db_md, (
        "MetaData mismatch: tenant model metadata is not db.metadata.\n"
        f"  model metadata id={id(model_md)}\n"
        f"  db.metadata id={id(db_md)}\n"
        "Two SQLAlchemy registries/bases are in play (usually import order)."
    )

    assert issubclass(M8flowTenantModel, SpiffworkflowBaseDBModel), (
        "Base mismatch: tenant model is not subclass of SpiffworkflowBaseDBModel.\n"
        f"  mro={M8flowTenantModel.mro()}"
    )

    tablename = getattr(M8flowTenantModel, "__tablename__", None)
    assert tablename, "M8flowTenantModel.__tablename__ missing."

    tables = db.metadata.tables
    if tablename not in tables:
        if all(tbl is not M8flowTenantModel.__table__ for tbl in tables.values()):
            raise AssertionError(
                "Tenant table not registered in db.metadata.tables.\n"
                f"  expected tablename='{tablename}'\n"
                f"  registered keys={sorted(tables.keys())}\n"
            )