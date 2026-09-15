"""Pluggable external-system integrations for m8flow-backend.

The first integration family here is ``auth`` — a provider-agnostic seam over
identity/authorization systems (Keycloak today). See ``auth.base`` for the
neutral interface and ``auth.keycloak`` for the concrete implementation.
"""
