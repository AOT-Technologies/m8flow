# extensions/m8flow-backend/src/m8flow_backend/services/secret_service_patch.py
from __future__ import annotations

import re

_PATCHED = False


def apply() -> None:
    """Patch SecretService to resolve only M8FLOW_SECRET:.

    The upstream library only recognises the ``SPIFF_SECRET:<name>`` sentinel
    when substituting secrets into BPMN task parameters.  This patch overrides
    ``resolve_possibly_secret_value`` so that workflow authors must use the
    M8Flow-branded prefix ``M8FLOW_SECRET:<name>`` instead.
    """
    global _PATCHED
    if _PATCHED:
        return

    from spiffworkflow_backend.services.secret_service import SecretService
    import sentry_sdk

    @classmethod  # type: ignore[misc]
    def _patched_resolve(cls, value: str) -> str:  # type: ignore[override]
        # Only handle the M8FLOW_SECRET: prefix, explicitly ignoring SPIFF_SECRET:.
        if "M8FLOW_SECRET:" in value:
            m8flow_match = re.match(r".*M8FLOW_SECRET:(?P<variable_name>\w+).*", value)
            if m8flow_match is not None:
                variable_name = m8flow_match.group("variable_name")
                secret = cls.get_secret(variable_name)
                with sentry_sdk.start_span(op="task", name="decrypt_secret"):
                    decrypted_value = cls._decrypt(secret.value)
                    value = re.sub(r"\bM8FLOW_SECRET:\w+", decrypted_value, value)

        return value

    SecretService.resolve_possibly_secret_value = _patched_resolve  # type: ignore[assignment]
    _PATCHED = True
