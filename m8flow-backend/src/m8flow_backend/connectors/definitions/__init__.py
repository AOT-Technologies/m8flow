"""Importing this package registers every connector definition."""

from m8flow_backend.connectors.definitions import (  # noqa: F401
    github,
    http,
    n8n,
    postgres,
    salesforce,
    slack,
    smtp,
    stripe,
)
