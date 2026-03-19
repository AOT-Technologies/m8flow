#!/usr/bin/env python3
"""Load sample template ZIP files into the database.

Run from the repo root with the backend virtualenv active:

    python extensions/m8flow-backend/bin/load_sample_templates.py

The script creates the Flask application, enters an app context, and
calls the sample template loader directly -- no need to restart the
server or set M8FLOW_LOAD_SAMPLE_TEMPLATES.

Existing templates with the same template_key (for the default tenant)
are silently skipped, so the script is safe to run multiple times.
"""
from __future__ import annotations

import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo_root))

from extensions.startup.sequence import create_application
from m8flow_backend.services.sample_template_loader import load_sample_templates


def main() -> None:
    app = create_application()
    flask_app = getattr(app, "app", app)
    loaded = load_sample_templates(flask_app)
    print(f"Done. {loaded} sample template(s) loaded.")


if __name__ == "__main__":
    main()
