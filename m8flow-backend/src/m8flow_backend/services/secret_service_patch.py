# m8flow-backend/src/m8flow_backend/services/secret_service_patch.py
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
    from m8flow_backend.services.secret_backend import get_secret_backend

    @classmethod  # type: ignore[misc]
    def _patched_add_secret(cls, key: str, value: str, user_id: int):  # type: ignore[override]
        return get_secret_backend().add_secret(key, value, user_id)

    @staticmethod
    def _patched_get_secret(key: str):  # type: ignore[override]
        return get_secret_backend().get_secret(key)

    @classmethod  # type: ignore[misc]
    def _patched_update_secret(
        cls,
        key: str,
        value: str,
        user_id: int | None = None,
        create_if_not_exists: bool | None = False,
    ) -> None:  # type: ignore[override]
        get_secret_backend().update_secret(
            key=key,
            value=value,
            user_id=user_id,
            create_if_not_exists=create_if_not_exists,
        )

    @staticmethod
    def _patched_delete_secret(key: str, user_id: int) -> None:  # type: ignore[override]
        get_secret_backend().delete_secret(key, user_id)

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

    SecretService.add_secret = _patched_add_secret  # type: ignore[assignment]
    SecretService.get_secret = _patched_get_secret  # type: ignore[assignment]
    SecretService.update_secret = _patched_update_secret  # type: ignore[assignment]
    SecretService.delete_secret = _patched_delete_secret  # type: ignore[assignment]
    SecretService.resolve_possibly_secret_value = _patched_resolve  # type: ignore[assignment]
    _PATCHED = True
