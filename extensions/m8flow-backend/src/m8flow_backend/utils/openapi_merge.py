import logging
import os
import yaml
import connexion
import spiffworkflow_backend

logger = logging.getLogger(__name__)

def patch_connexion_with_extension_spec(extension_api_path: str):
    """
    Monkey-patch connexion.FlaskApp.add_api to merge the extension API spec
    into the core API spec at runtime.
    """
    original_add_api = connexion.FlaskApp.add_api

    def unified_add_api(self, specification, **kwargs):
        # Check if this is the core API initialization (api.yml, possibly as full path from create_app)
        if os.path.basename(specification) == "api.yml":
            try:
                logger.info("Merging extension API spec into core API spec...")
                
                # 1. Load Core Spec
                core_spec_path = os.path.join(os.path.dirname(spiffworkflow_backend.__file__), "api.yml")
                with open(core_spec_path, 'r') as f:
                    core_spec = yaml.safe_load(f)
                
                # 2. Load Extension Spec
                if not os.path.exists(extension_api_path):
                     logger.error(f"Could not find M8Flow API spec at {extension_api_path}")
                     # Fallback: proceed with core only
                     return original_add_api(self, specification, **kwargs)

                with open(extension_api_path, 'r') as f:
                    ext_spec = yaml.safe_load(f)
                
                # 3. Define extension path prefix and root-level paths (no prefix)
                ext_prefix = "/m8flow"
                ROOT_LEVEL_EXTENSION_PATHS = ("/health",)

                # 4. Merge Paths - keep core paths unchanged, add extension paths with prefix
                # Core paths remain as-is; root-level extension paths stay as-is, others get /m8flow prefix
                for path, item in ext_spec.get('paths', {}).items():
                    prefixed_path = path if path in ROOT_LEVEL_EXTENSION_PATHS else f"{ext_prefix}{path}"
                    if prefixed_path in core_spec.get('paths', {}):
                        logger.warning(f"Path conflict: {prefixed_path} exists in both core and extension")
                    core_spec.setdefault('paths', {})[prefixed_path] = item
                
                # 5. Merge Components
                core_components = core_spec.setdefault('components', {})
                ext_components = ext_spec.get('components', {})
                
                core_schemas = core_components.setdefault('schemas', {})
                ext_schemas = ext_components.get('schemas', {})
                for schema_name, schema_def in ext_schemas.items():
                    if schema_name in core_schemas:
                        logger.warning(f"Schema conflict: {schema_name} exists in both core and extension")
                    core_schemas[schema_name] = schema_def
                
                # 6. Merge Tags
                core_tags = core_spec.setdefault('tags', [])
                ext_tags = ext_spec.get('tags', [])
                existing_tag_names = {tag.get('name') for tag in core_tags if isinstance(tag, dict)}
                for tag in ext_tags:
                    if isinstance(tag, dict) and tag.get('name') not in existing_tag_names:
                        core_tags.append(tag)
                
                # 7. Update Info (Title)
                if 'info' in core_spec:
                    core_spec['info']['title'] = "m8flow-backend"
                
                # 8. Keep original base_path - don't override it
                # This preserves core API routing at /v1.0/*
                # Extension APIs will be accessible at base_path + /m8flow/*
                
                logger.info(
                    "Successfully merged extension API spec. Root-level paths: %s; others under %s",
                    ROOT_LEVEL_EXTENSION_PATHS,
                    ext_prefix,
                )
                return original_add_api(self, core_spec, **kwargs)
                
            except Exception as e:
                logger.error(f"Failed to merge API specs: {e}", exc_info=True)
                # Fallback to original behavior
                return original_add_api(self, specification, **kwargs)
                
        return original_add_api(self, specification, **kwargs)

    connexion.FlaskApp.add_api = unified_add_api
