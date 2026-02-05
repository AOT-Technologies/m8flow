# extensions/m8flow-backend/src/m8flow_backend/services/authorization_service_patch.py
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_PATCHED = False

def apply() -> None:
    """Patch AuthorizationService.create_user_from_sign_in to handle uniquely identified usernames."""
    global _PATCHED
    if _PATCHED:
        return

    from spiffworkflow_backend.services.authorization_service import AuthorizationService
    
    original_create_user_from_sign_in = AuthorizationService.create_user_from_sign_in

    @classmethod
    def patched_create_user_from_sign_in(cls, user_info: dict[str, Any]):
        """
        Wrap create_user_from_sign_in to ensure username uniqueness across realms.
        We append the realm name (extracted from 'iss') to the preferred_username.
        """
        if "preferred_username" in user_info and "iss" in user_info:
            username = user_info["preferred_username"]
            iss = user_info["iss"]
            
            # Extract realm from issuer URL, e.g., http://.../realms/my-realm
            if "/realms/" in iss:
                realm = iss.split("/realms/")[-1].split("/")[0]
                # Only append if not already appended (idempotency)
                suffix = f"@{realm}"
                if not username.endswith(suffix):
                    user_info = user_info.copy()
                    user_info["preferred_username"] = f"{username}{suffix}"
                    logger.info(f"Transformed username '{username}' to '{user_info['preferred_username']}' for realm '{realm}'")
        
        return original_create_user_from_sign_in(user_info)

    AuthorizationService.create_user_from_sign_in = patched_create_user_from_sign_in
    _PATCHED = True
    logger.info("AuthorizationService.create_user_from_sign_in patched for unique multi-realm usernames.")
