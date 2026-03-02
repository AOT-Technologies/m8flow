"""
OpenAPI Merge Patch Service.

This module provides the patch to merge the M8Flow extension API spec
with the core SpiffWorkflow API spec at runtime.
"""
import logging
import os

from m8flow_backend.utils.openapi_merge import patch_connexion_with_extension_spec

logger = logging.getLogger(__name__)


def apply() -> None:
    """
    Apply the OpenAPI merge patch.
    
    This patches connexion.FlaskApp.add_api to merge the extension API spec
    into the core API spec before the app is created.
    """
    logger.info("Applying OpenAPI merge patch...")
    
    # Get the path to the extension API spec
    api_file_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "api.yml"
    )
    
    # Apply the patch
    patch_connexion_with_extension_spec(api_file_path)
    
    logger.info("OpenAPI merge patch applied successfully")
