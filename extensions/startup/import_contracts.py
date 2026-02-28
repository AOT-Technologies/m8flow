# extensions/startup/import_contracts.py
import importlib
from extensions.startup.guard import require_at_least, BootPhase, record_import

def import_spiff_db():
    require_at_least(BootPhase.POST_BOOTSTRAP, what="import spiffworkflow_backend.models.db")

    # Always record the contract call
    record_import("spiffworkflow_backend.models.db")

    db_mod = importlib.import_module("spiffworkflow_backend.models.db")
    return db_mod.db