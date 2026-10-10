"""Provider-agnostic auth flows and vocabulary (authProvider-analysis redesign).

- ``service.AuthService``: owns the flows (tenant switch, membership
  authority, platform-session detection, logout cleanup, neutral session view).
- ``switching``: ``SwitchMode`` / ``SwitchOutcome``.
- ``membership``: the pure "is the token's membership authoritative?" rule.
- ``cache``: the opt-in directory membership cache (disabled by default).
- ``contract``: the versioned m8flow claim an IdP may emit at mint time.
"""
from m8flow_backend.integrations.auth.core.service import CAPABILITY_NAMES, AuthService
from m8flow_backend.integrations.auth.core.switching import SwitchMode, SwitchOutcome

__all__ = ["CAPABILITY_NAMES", "AuthService", "SwitchMode", "SwitchOutcome"]
