"""Test-only building blocks for the auth-provider seam.

Not imported by any production code path -- see ``fake.py`` (the reference
``InMemoryAuthProvider``) and ``conformance.py`` (the provider-agnostic
contract suite both it and ``KeycloakAuthProvider`` run against). Built by
the auth-provider-seam wayfinder map's ticket 02.
"""
