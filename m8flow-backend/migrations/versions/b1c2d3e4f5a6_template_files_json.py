"""template_files_json: add files JSON column, migrate from bpmn_object_key, drop bpmn_object_key

Revision ID: b1c2d3e4f5a6
Revises: 9f2d0e4c8abc
Create Date: 2026-02-09

"""
from alembic import op
import sqlalchemy as sa
import os
import json
import logging

logger = logging.getLogger(__name__)


revision = "b1c2d3e4f5a6"
down_revision = "9f2d0e4c8abc"
branch_labels = None
depends_on = None


def _get_base_dir():
    base_dir = os.environ.get("M8FLOW_TEMPLATES_STORAGE_DIR")
    if not base_dir:
        bpmn_spec = os.environ.get("SPIFFWORKFLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR")
        if bpmn_spec:
            base_dir = os.path.join(bpmn_spec, "m8flow-templates")
    return os.path.abspath(base_dir) if base_dir else None


def _sanitize(s: str) -> str:
    invalid = ["/", "\\", ":", "*", "?", '"', "<", ">", "|"]
    for c in invalid:
        s = s.replace(c, "-")
    return s


def upgrade():
    op.add_column(
        "m8flow_templates",
        sa.Column("files", sa.JSON(), nullable=True),
    )

    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT id, m8f_tenant_id, template_key, version, bpmn_object_key FROM m8flow_templates"
        )
    )
    rows = result.fetchall()
    base_dir = _get_base_dir()

    for row in rows:
        id_, tenant_id, template_key, version, bpmn_object_key = row
        files_json = json.dumps([{"file_type": "bpmn", "file_name": bpmn_object_key}])

        if base_dir and bpmn_object_key:
            old_path = os.path.join(base_dir, tenant_id, bpmn_object_key)
            safe_key = _sanitize(template_key)
            safe_version = _sanitize(version)
            new_dir = os.path.join(base_dir, tenant_id, safe_key, safe_version)
            new_path = os.path.join(new_dir, bpmn_object_key)
            if os.path.isfile(old_path):
                try:
                    os.makedirs(new_dir, exist_ok=True)
                    with open(old_path, "rb") as f:
                        content = f.read()
                    with open(new_path, "wb") as f:
                        f.write(content)
                except (OSError, IOError) as e:
                    logger.warning("Failed to copy file from %s to %s: %s", old_path, new_path, e)

        conn.execute(
            sa.text("UPDATE m8flow_templates SET files = :files WHERE id = :id"),
            {"files": files_json, "id": id_},
        )

    op.drop_column("m8flow_templates", "bpmn_object_key")


def downgrade():
    op.add_column(
        "m8flow_templates",
        sa.Column("bpmn_object_key", sa.String(length=1024), nullable=True),
    )

    conn = op.get_bind()
    result = conn.execute(
        sa.text("SELECT id, m8f_tenant_id, template_key, version, files FROM m8flow_templates")
    )
    rows = result.fetchall()
    base_dir = _get_base_dir()

    for row in rows:
        id_, tenant_id, template_key, version, files = row
        bpmn_object_key = None
        if files and isinstance(files, list):
            for entry in files:
                if isinstance(entry, dict) and entry.get("file_type") == "bpmn":
                    bpmn_object_key = entry.get("file_name")
                    break
        if not bpmn_object_key:
            bpmn_object_key = "template.bpmn"

        conn.execute(
            sa.text(
                "UPDATE m8flow_templates SET bpmn_object_key = :key WHERE id = :id"
            ),
            {"key": bpmn_object_key, "id": id_},
        )

        if base_dir and bpmn_object_key:
            safe_key = _sanitize(template_key)
            safe_version = _sanitize(version)
            new_path = os.path.join(
                base_dir, tenant_id, safe_key, safe_version, bpmn_object_key
            )
            if os.path.isfile(new_path):
                old_dir = os.path.join(base_dir, tenant_id)
                os.makedirs(old_dir, exist_ok=True)
                old_path = os.path.join(old_dir, bpmn_object_key)
                try:
                    with open(new_path, "rb") as f:
                        content = f.read()
                    with open(old_path, "wb") as f:
                        f.write(content)
                except (OSError, IOError) as e:
                    logger.warning("Failed to copy file from %s to %s: %s", new_path, old_path, e)

    op.alter_column(
        "m8flow_templates",
        "bpmn_object_key",
        existing_type=sa.String(1024),
        nullable=False,
    )
    op.drop_column("m8flow_templates", "files")
