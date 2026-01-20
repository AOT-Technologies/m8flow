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
        # Check if this is the core API initialization ("api.yml" passed from create_app)
        if specification == "api.yml":
            try:
                logger.info("Merging extension API spec into core API spec...")
                
                # 1. Load Core Spec
                core_spec_path = os.path.join(os.path.dirname(spiffworkflow_backend.__file__), "api.yml")
                with open(core_spec_path, 'r') as f:
                    core_spec = yaml.safe_load(f)
                
                # 2. Get Core Base Path
                core_base_path = kwargs.get('base_path', '')
                
                # 3. Load Extension Spec
                if not os.path.exists(extension_api_path):
                     logger.error(f"Could not find M8Flow API spec at {extension_api_path}")
                     # Fallback not strictly necessary if we just want to fail or proceed with core, 
                     # but proceeding with core is safer.
                     return original_add_api(self, specification, **kwargs)

                with open(extension_api_path, 'r') as f:
                    ext_spec = yaml.safe_load(f)
                
                # 4. Define Extension Base Path
                ext_base_path = "/m8flow"
                
                # 5. Merge Paths (prepending base paths to create a unified root spec)
                new_paths = {}
                for path, item in core_spec.get('paths', {}).items():
                    new_paths[f"{core_base_path.rstrip('/')}{path}"] = item
                    
                for path, item in ext_spec.get('paths', {}).items():
                    new_paths[f"{ext_base_path.rstrip('/')}{path}"] = item
                
                core_spec['paths'] = new_paths
                
                # 6. Merge Components
                core_components = core_spec.setdefault('components', {})
                ext_components = ext_spec.get('components', {})
                
                core_schemas = core_components.setdefault('schemas', {})
                ext_schemas = ext_components.get('schemas', {})
                core_schemas.update(ext_schemas)
                
                # 7. Merge Tags
                core_tags = core_spec.setdefault('tags', [])
                ext_tags = ext_spec.get('tags', [])
                core_spec['tags'] = core_tags + ext_tags

                # 8. Update Info (Title)
                if 'info' in core_spec:
                    core_spec['info']['title'] = "m8flow-backend"
                
                # 9. Update Servers (Fix for blank servers list/incorrect base)
                # Since we are prepending paths manually and setting base_path to "/", 
                # we should set the server URL to root or remove the v1.0 suffix if present.
                core_spec['servers'] = [{'url': '/'}]
                
                # 10. Update base_path to root "/"
                kwargs['base_path'] = "/"
                
                return original_add_api(self, core_spec, **kwargs)
                
            except Exception as e:
                logger.error(f"Failed to merge API specs: {e}")
                # Fallback to original behavior
                return original_add_api(self, specification, **kwargs)
                
        return original_add_api(self, specification, **kwargs)

    connexion.FlaskApp.add_api = unified_add_api
