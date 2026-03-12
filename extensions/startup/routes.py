# extensions/startup/routes.py
import logging

logger = logging.getLogger(__name__)

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