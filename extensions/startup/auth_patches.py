# extensions/startup/auth_patches.py
import logging

from extensions.startup.patch_registry import POST_APP_EXTENSION_PATCH_SPECS, apply_patch_specs

logger = logging.getLogger(__name__)

def apply_extension_patches_after_app(flask_app) -> None:
    apply_patch_specs(POST_APP_EXTENSION_PATCH_SPECS, flask_app=flask_app, logger=logger)
