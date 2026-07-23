# extensions/startup/routes.py
import logging
import os

logger = logging.getLogger(__name__)


def register_root_route(app) -> None:
    """Register the public backend root landing page (M8F-409).

    The view function from root_controller is registered directly (not wrapped)
    so AuthorizationService.get_fully_qualified_api_function_from_request resolves
    it to m8flow_backend.routes.root_controller.root, which is auth-excluded.
    """
    from m8flow_backend.routes.root_controller import root

    rules = [("/", "m8flow_root")]
    wsgi_path_prefix = (os.environ.get("SPIFFWORKFLOW_BACKEND_WSGI_PATH_PREFIX") or "").strip()
    if wsgi_path_prefix and wsgi_path_prefix != "/":
        rules.append((f"{wsgi_path_prefix.rstrip('/')}/", "m8flow_root_prefixed"))

    for rule, endpoint in rules:
        try:
            app.add_url_rule(rule, endpoint, root, methods=["GET"])
        except Exception:
            logger.warning("Failed to register root route %s – may already exist", rule, exc_info=True)

def register_template_file_fallback_routes(app) -> None:
    from m8flow_backend.routes.templates_controller import template_put_file, template_delete_file

    base_path = app.config.get("SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX", "/v1.0")
    rule = f"{base_path}/m8flow/templates/<int:id>/files/<path:file_name>"

    def put_view(id: int, file_name: str):
        return template_put_file(id, file_name)

    def delete_view(id: int, file_name: str):
        return template_delete_file(id, file_name)

    try:
        app.add_url_rule(rule, "m8flow_template_put_file", put_view, methods=["PUT"])
        app.add_url_rule(rule, "m8flow_template_delete_file", delete_view, methods=["DELETE"])
    except Exception:
        logger.warning("Failed to register template file fallback routes – may already exist", exc_info=True)