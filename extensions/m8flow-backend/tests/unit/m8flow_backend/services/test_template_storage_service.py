# extensions/m8flow-backend/tests/unit/m8flow_backend/services/test_template_storage_service.py
import io
import os
import shutil
import tempfile
import zipfile

import pytest
from flask import Flask

from m8flow_backend.services.template_storage_service import (
    FilesystemTemplateStorageService,
    NoopTemplateStorageService,
    file_type_from_filename,
)
from spiffworkflow_backend.exceptions.api_error import ApiError


# ============================================================================
# file_type_from_filename tests
# ============================================================================


class TestFileTypeFromFilename:
    """Tests for the file_type_from_filename utility function."""

    def test_bpmn_extension(self) -> None:
        assert file_type_from_filename("diagram.bpmn") == "bpmn"

    def test_json_extension(self) -> None:
        assert file_type_from_filename("form.json") == "json"

    def test_dmn_extension(self) -> None:
        assert file_type_from_filename("rules.dmn") == "dmn"

    def test_md_extension(self) -> None:
        assert file_type_from_filename("readme.md") == "md"

    def test_unknown_txt_extension(self) -> None:
        assert file_type_from_filename("notes.txt") == "other"

    def test_unknown_csv_extension(self) -> None:
        assert file_type_from_filename("data.csv") == "other"

    def test_case_insensitive_bpmn(self) -> None:
        assert file_type_from_filename("Diagram.BPMN") == "bpmn"

    def test_case_insensitive_json(self) -> None:
        assert file_type_from_filename("Form.JSON") == "json"

    def test_case_insensitive_dmn(self) -> None:
        assert file_type_from_filename("Rules.DMN") == "dmn"

    def test_no_extension(self) -> None:
        assert file_type_from_filename("Makefile") == "other"

    def test_dotfile(self) -> None:
        assert file_type_from_filename(".gitignore") == "other"

    def test_multiple_dots(self) -> None:
        assert file_type_from_filename("my.diagram.bpmn") == "bpmn"

    def test_empty_string(self) -> None:
        assert file_type_from_filename("") == "other"


# ============================================================================
# FilesystemTemplateStorageService._sanitize tests
# ============================================================================


class TestSanitize:
    """Tests for the _sanitize static method."""

    def test_replaces_slashes(self) -> None:
        result = FilesystemTemplateStorageService._sanitize("a/b\\c")
        assert "/" not in result
        assert "\\" not in result

    def test_replaces_colon(self) -> None:
        result = FilesystemTemplateStorageService._sanitize("file:name")
        assert ":" not in result

    def test_replaces_special_characters(self) -> None:
        result = FilesystemTemplateStorageService._sanitize('file*name?<test>|"x"')
        for ch in ['*', '?', '<', '>', '|', '"']:
            assert ch not in result

    def test_strips_null_bytes(self) -> None:
        result = FilesystemTemplateStorageService._sanitize("file\x00name")
        assert "\x00" not in result
        assert "filename" in result.replace("-", "")

    def test_strips_leading_trailing_dots_spaces_hyphens(self) -> None:
        result = FilesystemTemplateStorageService._sanitize("...-hello-...")
        assert not result.startswith(".")
        assert not result.startswith("-")
        assert not result.endswith(".")
        assert not result.endswith("-")
        assert "hello" in result

    def test_raises_for_empty_after_sanitization(self) -> None:
        with pytest.raises(ApiError) as exc_info:
            FilesystemTemplateStorageService._sanitize("...")
        assert exc_info.value.status_code == 400

    def test_raises_for_empty_string(self) -> None:
        with pytest.raises(ApiError) as exc_info:
            FilesystemTemplateStorageService._sanitize("")
        assert exc_info.value.status_code == 400

    def test_truncates_long_names(self) -> None:
        long_name = "a" * 300
        result = FilesystemTemplateStorageService._sanitize(long_name)
        assert len(result) <= 255

    def test_preserves_normal_names(self) -> None:
        result = FilesystemTemplateStorageService._sanitize("my-template_v1")
        assert result == "my-template_v1"

    def test_preserves_alphanumeric(self) -> None:
        result = FilesystemTemplateStorageService._sanitize("hello123")
        assert result == "hello123"


# ============================================================================
# FilesystemTemplateStorageService integration tests (with temp directory)
# ============================================================================


@pytest.fixture()
def storage_app():
    """Create a Flask app with a temp directory for storage tests."""
    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    tmpdir = tempfile.mkdtemp(prefix="test_storage_")
    app.config["TESTING"] = True
    app.config["M8FLOW_TEMPLATES_STORAGE_DIR"] = tmpdir
    yield app, tmpdir
    shutil.rmtree(tmpdir, ignore_errors=True)


class TestFilesystemStorageService:
    """Integration tests for FilesystemTemplateStorageService with a real temp directory."""

    def test_store_and_get_file_roundtrip(self, storage_app: tuple) -> None:
        """Store bytes, retrieve same bytes."""
        app, _ = storage_app
        svc = FilesystemTemplateStorageService()
        content = b"<bpmn>test content</bpmn>"

        with app.app_context():
            svc.store_file("tenant-a", "my-template", "V1", "diagram.bpmn", "bpmn", content)
            result = svc.get_file("tenant-a", "my-template", "V1", "diagram.bpmn")

        assert result == content

    def test_get_file_missing_raises_404(self, storage_app: tuple) -> None:
        """get_file for missing file raises ApiError with 404."""
        app, _ = storage_app
        svc = FilesystemTemplateStorageService()

        with app.app_context():
            with pytest.raises(ApiError) as exc_info:
                svc.get_file("tenant-a", "nonexistent", "V1", "missing.bpmn")
            assert exc_info.value.status_code == 404

    def test_list_files_returns_correct_list(self, storage_app: tuple) -> None:
        """list_files returns correct file list for a version directory."""
        app, _ = storage_app
        svc = FilesystemTemplateStorageService()

        with app.app_context():
            svc.store_file("tenant-a", "tpl", "V1", "diagram.bpmn", "bpmn", b"bpmn content")
            svc.store_file("tenant-a", "tpl", "V1", "form.json", "json", b'{"key":"value"}')
            svc.store_file("tenant-a", "tpl", "V1", "rules.dmn", "dmn", b"dmn content")

            files = svc.list_files("tenant-a", "tpl", "V1")

        names = sorted(f["file_name"] for f in files)
        types = {f["file_name"]: f["file_type"] for f in files}
        assert names == ["diagram.bpmn", "form.json", "rules.dmn"]
        assert types["diagram.bpmn"] == "bpmn"
        assert types["form.json"] == "json"
        assert types["rules.dmn"] == "dmn"

    def test_list_files_empty_directory(self, storage_app: tuple) -> None:
        """list_files returns empty list for non-existent version directory."""
        app, _ = storage_app
        svc = FilesystemTemplateStorageService()

        with app.app_context():
            files = svc.list_files("tenant-a", "nonexistent", "V1")

        assert files == []

    def test_delete_file_removes_from_storage(self, storage_app: tuple) -> None:
        """delete_file removes the file from storage."""
        app, _ = storage_app
        svc = FilesystemTemplateStorageService()

        with app.app_context():
            svc.store_file("tenant-a", "tpl", "V1", "temp.bpmn", "bpmn", b"temp content")
            # Verify it exists
            assert svc.get_file("tenant-a", "tpl", "V1", "temp.bpmn") == b"temp content"
            # Delete it
            svc.delete_file("tenant-a", "tpl", "V1", "temp.bpmn")
            # Verify it's gone
            with pytest.raises(ApiError) as exc_info:
                svc.get_file("tenant-a", "tpl", "V1", "temp.bpmn")
            assert exc_info.value.status_code == 404

    def test_delete_file_nonexistent_is_silent(self, storage_app: tuple) -> None:
        """delete_file for nonexistent file does not raise."""
        app, _ = storage_app
        svc = FilesystemTemplateStorageService()

        with app.app_context():
            # Should not raise
            svc.delete_file("tenant-a", "tpl", "V1", "nonexistent.bpmn")

    def test_stream_zip_creates_valid_zip(self, storage_app: tuple) -> None:
        """stream_zip creates a valid zip with the expected files."""
        app, _ = storage_app
        svc = FilesystemTemplateStorageService()

        with app.app_context():
            svc.store_file("tenant-a", "tpl", "V1", "diagram.bpmn", "bpmn", b"bpmn data")
            svc.store_file("tenant-a", "tpl", "V1", "form.json", "json", b'{"k":"v"}')

            file_entries = [
                {"file_name": "diagram.bpmn", "file_type": "bpmn"},
                {"file_name": "form.json", "file_type": "json"},
            ]
            zip_bytes = svc.stream_zip("tenant-a", "tpl", "V1", file_entries)

        # Verify it's a valid zip
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            names = sorted(zf.namelist())
            assert names == ["diagram.bpmn", "form.json"]
            assert zf.read("diagram.bpmn") == b"bpmn data"
            assert zf.read("form.json") == b'{"k":"v"}'

    def test_stream_zip_skips_missing_files(self, storage_app: tuple) -> None:
        """stream_zip logs a warning and skips missing files."""
        app, _ = storage_app
        svc = FilesystemTemplateStorageService()

        with app.app_context():
            svc.store_file("tenant-a", "tpl", "V1", "diagram.bpmn", "bpmn", b"bpmn data")

            file_entries = [
                {"file_name": "diagram.bpmn", "file_type": "bpmn"},
                {"file_name": "missing.json", "file_type": "json"},
            ]
            zip_bytes = svc.stream_zip("tenant-a", "tpl", "V1", file_entries)

        # The zip should only contain the file that exists
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            names = zf.namelist()
            assert "diagram.bpmn" in names
            assert "missing.json" not in names

    def test_stream_zip_empty_entries(self, storage_app: tuple) -> None:
        """stream_zip with empty file_entries produces a valid empty zip."""
        app, _ = storage_app
        svc = FilesystemTemplateStorageService()

        with app.app_context():
            zip_bytes = svc.stream_zip("tenant-a", "tpl", "V1", [])

        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            assert len(zf.namelist()) == 0

    def test_store_file_creates_directories(self, storage_app: tuple) -> None:
        """store_file creates nested directories if they don't exist."""
        app, tmpdir = storage_app
        svc = FilesystemTemplateStorageService()

        with app.app_context():
            svc.store_file("new-tenant", "new-tpl", "V1", "new.bpmn", "bpmn", b"content")
            # Verify the directory structure was created
            expected_dir = os.path.join(tmpdir, "new-tenant", "new-tpl", "V1")
            assert os.path.isdir(expected_dir)
            assert os.path.isfile(os.path.join(expected_dir, "new.bpmn"))

    def test_store_file_overwrites_existing(self, storage_app: tuple) -> None:
        """store_file overwrites an existing file with the same name."""
        app, _ = storage_app
        svc = FilesystemTemplateStorageService()

        with app.app_context():
            svc.store_file("tenant-a", "tpl", "V1", "diagram.bpmn", "bpmn", b"original")
            svc.store_file("tenant-a", "tpl", "V1", "diagram.bpmn", "bpmn", b"updated")
            result = svc.get_file("tenant-a", "tpl", "V1", "diagram.bpmn")

        assert result == b"updated"


# ============================================================================
# NoopTemplateStorageService tests
# ============================================================================


class TestNoopStorageService:
    """All methods raise NotImplementedError."""

    def test_store_file_raises(self) -> None:
        svc = NoopTemplateStorageService()
        with pytest.raises(NotImplementedError):
            svc.store_file("t", "k", "v", "f", "bpmn", b"data")

    def test_get_file_raises(self) -> None:
        svc = NoopTemplateStorageService()
        with pytest.raises(NotImplementedError):
            svc.get_file("t", "k", "v", "f")

    def test_list_files_raises(self) -> None:
        svc = NoopTemplateStorageService()
        with pytest.raises(NotImplementedError):
            svc.list_files("t", "k", "v")

    def test_delete_file_raises(self) -> None:
        svc = NoopTemplateStorageService()
        with pytest.raises(NotImplementedError):
            svc.delete_file("t", "k", "v", "f")

    def test_stream_zip_raises(self) -> None:
        svc = NoopTemplateStorageService()
        with pytest.raises(NotImplementedError):
            svc.stream_zip("t", "k", "v", [])
