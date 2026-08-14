"""PostgreSQL connector (postgres_v2).

The credential parameter is ``database_connection_str`` - the name the
sartography connector's V2 commands use, and the one the shipped PostgreSQL
sample template writes. It is deliberately not ``connection_string``.
"""

from __future__ import annotations

from m8flow_backend.connectors.base import (
    ConnectorDefinition,
    FieldGroup,
    secret_param,
)
from m8flow_backend.connectors.registry import register


@register
class PostgresConnector(ConnectorDefinition):
    connector_type = "postgres_v2"
    display_name = "PostgreSQL"
    description = "Execute PostgreSQL database operations"
    category = "data"
    icon = "database"
    docs_anchor = "#postgresql-connector-postgres_v2"
    groups = (FieldGroup(id="connection", label="Connection"),)

    fields = (
        secret_param(
            "database_connection_str",
            "Connection String",
            group="connection",
            help_text=(
                "dbname=databasename user=username password=password host=hostname port=portnumber"
            ),
        ),
    )
