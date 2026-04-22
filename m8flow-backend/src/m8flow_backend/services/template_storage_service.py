from __future__ import annotations

import io
import logging
import os
import zipfile
from typing import Protocol

from flask import current_app

from spiffworkflow_backend.exceptions.api_error import ApiError

logger = logging.getLogger(__name__)

FILE_EXT_TO_TYPE = {
    ".bpmn": "bpmn",
    ".json": "json",
    ".dmn": "dmn",
    ".md": "md",
}


def file_type_from_filename(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    return FILE_EXT_TO_TYPE.get(ext, "other")


class TemplateStorageService(Protocol):
    """Abstraction for storing and retrieving template files."""

    def store_file(
        self,
        tenant_id: str,
        template_key: str,
        version: str,
        file_name: str,
        file_type: str,
        content: bytes,
    ) -> None:
        """Persist a file under {tenant_id}/{template_key}/{version}/{file_name}."""
        ...

    def get_file(
        self,
        tenant_id: str,
        template_key: str,
        version: str,
        file_name: str,
    ) -> bytes:
        """Retrieve file content by path."""
        ...

    def list_files(
        self,
        tenant_id: str,
        template_key: str,
        version: str,
    ) -> list[dict]:
        """List files under version prefix. Returns [{"file_name": str, "file_type": str}]."""
        ...

    def delete_file(
        self,
        tenant_id: str,
        template_key: str,
        version: str,
        file_name: str,
    ) -> None:
        """Remove a single file (for replace/delete)."""
        ...

    def stream_zip(
        self,
        tenant_id: str,
        template_key: str,
        version: str,
        file_entries: list[dict],
    ) -> bytes:
        """Build a zip of the given file entries (each has file_name, file_type). Returns zip bytes."""
        ...


class NoopTemplateStorageService:
    """Placeholder storage."""

    def store_file(
        self,
        tenant_id: str,
        template_key: str,
        version: str,
        file_name: str,
        file_type: str,
        content: bytes,
    ) -> None:
        raise NotImplementedError("Template storage is not configured.")

    def get_file(
        self,
        tenant_id: str,
        template_key: str,
        version: str,
        file_name: str,
    ) -> bytes:
        raise NotImplementedError("Template storage is not configured.")

    def list_files(
        self,
        tenant_id: str,
        template_key: str,
        version: str,
    ) -> list[dict]:
        raise NotImplementedError("Template storage is not configured.")

    def delete_file(
        self,
        tenant_id: str,
        template_key: str,
        version: str,
        file_name: str,
    ) -> None:
        raise NotImplementedError("Template storage is not configured.")

    def stream_zip(
        self,
        tenant_id: str,
        template_key: str,
        version: str,
        file_entries: list[dict],
    ) -> bytes:
        raise NotImplementedError("Template storage is not configured.")


class FilesystemTemplateStorageService:
    """Stores template files on the local filesystem at {base_dir}/{tenant_id}/{template_key}/{version}/{file_name}."""

    @staticmethod
    def _get_base_dir() -> str:
        base_dir = current_app.config.get("M8FLOW_TEMPLATES_STORAGE_DIR")
        if not base_dir:
            bpmn_spec_dir = current_app.config.get(
                "SPIFFWORKFLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR"
            )
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
    def _sanitize(s: str) -> str:
        """Sanitize a path component: strip null bytes, replace invalid chars, enforce length."""
        s = s.replace("\x00", "")
        invalid = ["/", "\\", ":", "*", "?", '"', "<", ">", "|"]
        for c in invalid:
            s = s.replace(c, "-")
        s = s.strip(". -")
        if not s:
            raise ApiError("invalid_input", "Name is empty after sanitization", status_code=400)
        if len(s) > 255:
            s = s[:255]
        return s

    def _version_dir(self, tenant_id: str, template_key: str, version: str) -> str:
        base = self._get_base_dir()
        return os.path.join(
            base,
            self._sanitize(tenant_id),
            self._sanitize(template_key),
            self._sanitize(version),
        )

    def _file_path(
        self,
        tenant_id: str,
        template_key: str,
        version: str,
        file_name: str,
    ) -> str:
        safe_name = self._sanitize(os.path.basename(file_name))
        return os.path.join(
            self._version_dir(tenant_id, template_key, version),
            safe_name,
        )

    def store_file(
        self,
        tenant_id: str,
        template_key: str,
        version: str,
        file_name: str,
        file_type: str,
        content: bytes,
    ) -> None:
        path = self._file_path(tenant_id, template_key, version, file_name)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(content)
        except (IOError, OSError) as e:
            raise ApiError(
                "storage_error",
                f"Failed to write file: {str(e)}",
                status_code=500,
            )

    def get_file(
        self,
        tenant_id: str,
        template_key: str,
        version: str,
        file_name: str,
    ) -> bytes:
        path = self._file_path(tenant_id, template_key, version, file_name)
        if not os.path.isfile(path):
            raise ApiError(
                "not_found",
                f"File not found: {file_name}",
                status_code=404,
            )
        try:
            with open(path, "rb") as f:
                return f.read()
        except (IOError, OSError) as e:
            raise ApiError(
                "storage_error",
                f"Failed to read file: {str(e)}",
                status_code=500,
            )

    def list_files(
        self,
        tenant_id: str,
        template_key: str,
        version: str,
    ) -> list[dict]:
        vdir = self._version_dir(tenant_id, template_key, version)
        if not os.path.isdir(vdir):
            return []
        result = []
        for name in os.listdir(vdir):
            path = os.path.join(vdir, name)
            if os.path.isfile(path):
                result.append({
                    "file_name": name,
                    "file_type": file_type_from_filename(name),
                })
        return result

    def delete_file(
        self,
        tenant_id: str,
        template_key: str,
        version: str,
        file_name: str,
    ) -> None:
        path = self._file_path(tenant_id, template_key, version, file_name)
        if os.path.isfile(path):
            try:
                os.remove(path)
            except (IOError, OSError) as e:
                raise ApiError(
                    "storage_error",
                    f"Failed to delete file: {str(e)}",
                    status_code=500,
                )

    def stream_zip(
        self,
        tenant_id: str,
        template_key: str,
        version: str,
        file_entries: list[dict],
    ) -> bytes:
        buf = io.BytesIO()
        skipped: list[str] = []
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for entry in file_entries:
                name = entry.get("file_name")
                if not name:
                    continue
                try:
                    content = self.get_file(tenant_id, template_key, version, name)
                    zf.writestr(name, content)
                except ApiError:
                    logger.warning(
                        "Skipping missing file during zip export: %s/%s/%s/%s",
                        tenant_id, template_key, version, name,
                    )
                    skipped.append(name)
        if skipped:
            logger.warning(
                "Zip export for %s/%s/%s skipped %d file(s): %s",
                tenant_id, template_key, version, len(skipped), ", ".join(skipped),
            )
        return buf.getvalue()
