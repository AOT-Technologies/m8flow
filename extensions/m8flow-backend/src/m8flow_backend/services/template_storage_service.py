from __future__ import annotations

import os
from typing import Protocol

from flask import current_app

from spiffworkflow_backend.exceptions.api_error import ApiError


class TemplateStorageService(Protocol):
    """Abstraction for storing and retrieving BPMN content."""

    def store_bpmn(self, template_key: str, version: str, bpmn_bytes: bytes, tenant_id: str) -> str:
        """Persist BPMN content and return filename only (e.g., 'template-key.bpmn')."""
        ...

    def get_bpmn(self, filename: str, tenant_id: str) -> bytes:
        """Retrieve BPMN content by filename and tenant_id."""
        ...


class NoopTemplateStorageService:
    """Placeholder storage that assumes BPMN is already stored and key is provided."""

    def store_bpmn(self, template_key: str, version: str, bpmn_bytes: bytes, tenant_id: str) -> str:
        raise NotImplementedError("BPMN storage is not configured; provide bpmn_object_key directly.")

    def get_bpmn(self, filename: str, tenant_id: str) -> bytes:
        raise NotImplementedError("BPMN storage is not configured; cannot fetch BPMN content.")


class FilesystemTemplateStorageService:
    """Stores BPMN templates on the local filesystem in m8flow-specific directory."""

    @staticmethod
    def _get_base_dir() -> str:
        """Get m8flow templates base directory from Flask config."""
        # Try m8flow-specific directory first
        base_dir = current_app.config.get("M8FLOW_TEMPLATES_STORAGE_DIR")

        if not base_dir:
            # Fallback to subdirectory of BPMN spec dir for backward compatibility
            bpmn_spec_dir = current_app.config.get("SPIFFWORKFLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR")
            if bpmn_spec_dir:
                base_dir = os.path.join(bpmn_spec_dir, "m8flow-templates")
            else:
                raise ApiError(
                    "configuration_error",
                    "M8FLOW_TEMPLATES_STORAGE_DIR or SPIFFWORKFLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR must be configured",
                    status_code=500,
                )

        return os.path.abspath(base_dir)

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        """Remove invalid filesystem characters from filename."""
        invalid_chars = ["/", "\\", ":", "*", "?", '"', "<", ">", "|"]
        for char in invalid_chars:
            filename = filename.replace(char, "-")
        return filename

    def store_bpmn(self, template_key: str, version: str, bpmn_bytes: bytes, tenant_id: str) -> str:
        """Store BPMN content and return filename only (e.g., 'template-key_V2.bpmn')."""
        base_dir = self._get_base_dir()
        safe_key = self._sanitize_filename(template_key)
        safe_version = self._sanitize_filename(version)
        filename = f"{safe_key}_{safe_version}.bpmn"
        # Store at: {base_dir}/{tenant_id}/{filename}
        full_path = os.path.join(base_dir, tenant_id, filename)

        # Create directory if needed
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        # Write file
        try:
            with open(full_path, "wb") as f:
                f.write(bpmn_bytes)
        except (IOError, OSError) as e:
            raise ApiError("storage_error", f"Failed to write BPMN file: {str(e)}", status_code=500)

        # Return only filename for database storage
        return filename

    def get_bpmn(self, filename: str, tenant_id: str) -> bytes:
        """Retrieve BPMN content by filename and tenant_id."""
        base_dir = self._get_base_dir()
        # Reconstruct full path: {base_dir}/{tenant_id}/{filename}
        full_path = os.path.join(base_dir, tenant_id, filename)

        if not os.path.exists(full_path):
            raise ApiError("not_found", f"BPMN file not found: {filename} for tenant {tenant_id}", status_code=404)

        try:
            with open(full_path, "rb") as f:
                return f.read()
        except FileNotFoundError:
            # File might have been removed after the exists() check
            raise ApiError("not_found", f"BPMN file not found: {filename} for tenant {tenant_id}", status_code=404)
        except (IOError, OSError) as e:
            raise ApiError("storage_error", f"Failed to read BPMN file: {str(e)}", status_code=500)
