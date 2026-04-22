"""tenant_scope_process_model_template: change unique constraint to be tenant-scoped

Revision ID: g7b8c9d0e1f2
Revises: d2b8f0d1a4c5
Create Date: 2026-04-06

This migration changes the unique constraint on process_model_identifier in the
m8flow_process_model_template table from global uniqueness to tenant-scoped
uniqueness. This allows different tenants to create process models with the
same identifier from shared templates.
"""
from alembic import op
import sqlalchemy as sa


revision = "g7b8c9d0e1f2"
down_revision = "d2b8f0d1a4c5"
branch_labels = None
depends_on = None

TABLE_NAME = "m8flow_process_model_template"


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _drop_unique_constraint(table: str, columns: list[str]) -> None:
    """Drop a unique constraint by its columns, handling both constraint and index cases."""
    insp = _inspector()
    for uc in insp.get_unique_constraints(table):
        if set(uc.get("column_names", [])) == set(columns):
            op.drop_constraint(uc["name"], table, type_="unique")
            return
    for idx in insp.get_indexes(table):
        if idx.get("unique") and set(idx.get("column_names", [])) == set(columns):
            op.drop_index(idx["name"], table_name=table)
            return


def upgrade() -> None:
    _drop_unique_constraint(TABLE_NAME, ["process_model_identifier"])

    op.create_unique_constraint(
        "uq_process_model_identifier_tenant",
        TABLE_NAME,
        ["m8f_tenant_id", "process_model_identifier"],
    )


def downgrade() -> None:
    _drop_unique_constraint(TABLE_NAME, ["m8f_tenant_id", "process_model_identifier"])

    op.create_unique_constraint(
        "m8flow_process_model_template_process_model_identifier_key",
        TABLE_NAME,
        ["process_model_identifier"],
    )
