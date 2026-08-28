"""PostgreSQL connector.

The whole credential is one psycopg2 connection string, so the profile holds a
single secret field. Verified against the
"postgresql-table-lifecycle-management" sample template.
"""

from __future__ import annotations

from typing import Annotated, ClassVar

from m8flow_backend.connectors.base import (
    ConnectorDefinition,
    secret_param,
    task_param,
)
from m8flow_backend.connectors.registry import register


@register
class PostgresConnector(ConnectorDefinition):
    id: ClassVar[str] = "m8flow.postgres_v2.v1"
    connector_type: ClassVar[str] = "postgres_v2"
    display_name: ClassVar[str] = "PostgreSQL"
    description: ClassVar[str] = "Execute PostgreSQL database operations"
    category: ClassVar[str] = "database"
    icon: ClassVar[str] = "database"
    docs_anchor: ClassVar[str] = "postgresql-connector-postgres_v2"
    groups: ClassVar[tuple[dict[str, str], ...]] = (
        {"id": "connection", "label": "Connection"},
    )

    database_connection_str: Annotated[str, secret_param(
        "connection", label="Connection String",
        help_text="dbname=mydb user=myuser password=... host=hostname port=5432")]

    table_name: Annotated[str | None, task_param(label="Table Name")]
    # Declared as sql_schema because a field literally named `schema` shadows
    # pydantic's deprecated BaseModel.schema(). `wire_name` carries the name the
    # proxy actually expects, which the descriptor and the runtime patch use.
    sql_schema: Annotated[str | None, task_param(
        label="Schema", widget="textarea", wire_name="schema",
        help_text='Command payload, e.g. {"sql": "SELECT 1"}.')]
