#!/usr/bin/env python
"""Dump the ORM's view of the schema, for before/after comparison.

Needs no database. Use it to check that a change to the models or to
m8flow_backend.models.tenant_schema leaves the SQLAlchemy metadata as intended.

Usage:
    python bin/dump-model-metadata.py > after.json
    git stash && python bin/dump-model-metadata.py > before.json && git stash pop
    # then diff the two
"""
from __future__ import annotations

import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "m8flow-backend" / "src"))
sys.path.insert(0, str(REPO / "spiffworkflow-backend" / "src"))

from m8flow_backend.services import model_override_patch  # noqa: E402

model_override_patch.apply()

import spiffworkflow_backend.load_database_models  # noqa: E402,F401

# m8flow's own models are registered here, not by upstream's loader.
import m8flow_backend.models._timestamps_bootstrap  # noqa: E402,F401

# m8flow's additions to upstream's models, configured once they are imported -
# exactly as migrations/env.py and the app boot sequence do it.
try:
    from m8flow_backend.models import tenant_schema  # noqa: E402

    tenant_schema.configure()
except ImportError:
    # Running against the pre-change code, where tenant_schema does not exist.
    print("note: tenant_schema not present (pre-change code)", file=sys.stderr)

from spiffworkflow_backend.models.db import db  # noqa: E402

out: dict[str, dict] = {}
for name, table in sorted(db.Model.metadata.tables.items()):
    out[name] = {
        "columns": {
            c.name: {
                "type": str(c.type),
                "nullable": c.nullable,
                "primary_key": c.primary_key,
                "unique": bool(c.unique),
                "default": str(c.default) if c.default is not None else None,
                "foreign_keys": sorted(fk.target_fullname for fk in c.foreign_keys),
            }
            for c in table.columns
        },
        "indexes": sorted(
            f"{i.name}({','.join(c.name for c in i.columns)})" for i in table.indexes
        ),
        "unique_constraints": sorted(
            f"{con.name}({','.join(c.name for c in con.columns)})"
            for con in table.constraints
            if con.__class__.__name__ == "UniqueConstraint"
        ),
        "foreign_key_constraints": sorted(
            f"{','.join(c.name for c in con.columns)}->{sorted(e.target_fullname for e in con.elements)}"
            for con in table.constraints
            if con.__class__.__name__ == "ForeignKeyConstraint"
        ),
    }

print(json.dumps(out, indent=2, sort_keys=True))
print(f"tables: {len(out)}", file=sys.stderr)
