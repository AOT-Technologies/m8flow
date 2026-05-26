"""Tests for SoftDeleteService."""
from __future__ import annotations

import json
import os
import time
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask, g

from m8flow_backend.tenancy import clear_tenant_context
from spiffworkflow_backend.exceptions.api_error import ApiError
from spiffworkflow_backend.services.file_system_service import FileSystemService
from spiffworkflow_backend.services.process_model_service import (
    ProcessModelService,
    ProcessModelWithInstancesNotDeletableError,
)


@pytest.fixture(autouse=True)
def _isolate_soft_delete():
    clear_tenant_context()
    yield
    clear_tenant_context()


def _write_minimal_process_group(dir_path: str, name: str = "G") -> None:
    os.makedirs(dir_path, exist_ok=True)
    path = os.path.join(dir_path, FileSystemService.PROCESS_GROUP_JSON_FILE)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"display_name": name, "description": ""}, f)


def _write_minimal_process_model(dir_path: str, name: str = "M") -> None:
    os.makedirs(dir_path, exist_ok=True)
    path = os.path.join(dir_path, FileSystemService.PROCESS_MODEL_JSON_FILE)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"display_name": name, "description": ""}, f)


@pytest.fixture()
def bpmn_root(tmp_path):
    root = tmp_path / "bpmn_specs"
    root.mkdir()
    _write_minimal_process_group(str(root / "group1"))
    _write_minimal_process_model(str(root / "group1" / "model1"), "Model 1")
    _write_minimal_process_model(str(root / "group1" / "model2"), "Model 2")
    return str(root)


@pytest.fixture()
def app_with_db(bpmn_root):
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SPIFFWORKFLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR"] = bpmn_root
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    from spiffworkflow_backend.models.db import db

    db.init_app(app)
    with app.app_context():
        db.create_all()
        yield app


class TestSoftDeleteServiceIdentifierCheck:
    def test_is_soft_deleted_identifier_true(self):
        from m8flow_backend.services.soft_delete_service import SoftDeleteService

        assert SoftDeleteService.is_soft_deleted_identifier("group1/model1_deleted_1716000000")
        assert SoftDeleteService.is_soft_deleted_identifier("model_deleted_9999999999")
        assert SoftDeleteService.is_soft_deleted_identifier("a/b/c_deleted_123")

    def test_is_soft_deleted_identifier_false(self):
        from m8flow_backend.services.soft_delete_service import SoftDeleteService

        assert not SoftDeleteService.is_soft_deleted_identifier("group1/model1")
        assert not SoftDeleteService.is_soft_deleted_identifier("model_deleted")
        assert not SoftDeleteService.is_soft_deleted_identifier("model_deleted_abc")
        assert not SoftDeleteService.is_soft_deleted_identifier("")


class TestSoftDeleteProcessModel:
    @patch("spiffworkflow_backend.routes.process_api_blueprint._commit_and_push_to_git")
    def test_soft_delete_renames_directory(self, mock_git, app_with_db, bpmn_root):
        from spiffworkflow_backend.models.db import db
        from m8flow_backend.services.soft_delete_service import SoftDeleteService
        from m8flow_backend.models.process_model_deletion import ProcessModelDeletionModel, DeletionStatus

        with app_with_db.test_request_context("/"):
            g.m8flow_tenant_id = "test-tenant"
            user = MagicMock()
            user.username = "admin@test.com"

            original_path = os.path.join(bpmn_root, "group1", "model1")
            assert os.path.exists(original_path)

            deletion = SoftDeleteService.soft_delete_process_model("group1/model1", user=user)

            assert not os.path.exists(original_path)
            assert deletion.original_identifier == "group1/model1"
            assert deletion.status == DeletionStatus.SOFT_DELETED.value
            assert deletion.deleted_by == "admin@test.com"
            assert "_deleted_" in deletion.deleted_identifier

            deleted_path = FileSystemService.full_path_from_id(deletion.deleted_identifier)
            assert os.path.exists(deleted_path)

    @patch("spiffworkflow_backend.routes.process_api_blueprint._commit_and_push_to_git")
    def test_soft_delete_inserts_db_row(self, mock_git, app_with_db, bpmn_root):
        from spiffworkflow_backend.models.db import db
        from m8flow_backend.services.soft_delete_service import SoftDeleteService
        from m8flow_backend.models.process_model_deletion import ProcessModelDeletionModel, DeletionStatus

        with app_with_db.test_request_context("/"):
            g.m8flow_tenant_id = "test-tenant"
            user = MagicMock()
            user.username = "admin@test.com"

            SoftDeleteService.soft_delete_process_model("group1/model1", user=user)

            rows = ProcessModelDeletionModel.query.all()
            assert len(rows) == 1
            assert rows[0].m8f_tenant_id == "test-tenant"
            assert rows[0].display_name == "Model 1"


class TestSoftDeleteProcessGroup:
    @patch("spiffworkflow_backend.routes.process_api_blueprint._commit_and_push_to_git")
    def test_soft_delete_group_renames_directory(self, mock_git, app_with_db, bpmn_root):
        from spiffworkflow_backend.models.db import db
        from m8flow_backend.services.soft_delete_service import SoftDeleteService
        from m8flow_backend.models.process_group_deletion import ProcessGroupDeletionModel, DeletionStatus

        with app_with_db.test_request_context("/"):
            g.m8flow_tenant_id = "test-tenant"
            user = MagicMock()
            user.username = "admin@test.com"

            original_path = os.path.join(bpmn_root, "group1")
            assert os.path.exists(original_path)

            deletion = SoftDeleteService.soft_delete_process_group("group1", user=user)

            assert not os.path.exists(original_path)
            assert deletion.original_identifier == "group1"
            assert "_deleted_" in deletion.deleted_identifier


class TestRestoreProcessModel:
    @patch("spiffworkflow_backend.routes.process_api_blueprint._commit_and_push_to_git")
    def test_restore_with_original_name_available(self, mock_git, app_with_db, bpmn_root):
        from spiffworkflow_backend.models.db import db
        from m8flow_backend.services.soft_delete_service import SoftDeleteService
        from m8flow_backend.models.process_model_deletion import ProcessModelDeletionModel, DeletionStatus

        with app_with_db.test_request_context("/"):
            g.m8flow_tenant_id = "test-tenant"
            user = MagicMock()
            user.username = "admin@test.com"

            deletion = SoftDeleteService.soft_delete_process_model("group1/model1", user=user)

            process_model = SoftDeleteService.restore_process_model(deletion.id, user=user)
            assert process_model is not None

            original_path = os.path.join(bpmn_root, "group1", "model1")
            assert os.path.exists(original_path)

            row = db.session.get(ProcessModelDeletionModel, deletion.id)
            assert row.status == DeletionStatus.RESTORED.value

    @patch("spiffworkflow_backend.routes.process_api_blueprint._commit_and_push_to_git")
    def test_restore_with_name_conflict_raises_error(self, mock_git, app_with_db, bpmn_root):
        from spiffworkflow_backend.models.db import db
        from m8flow_backend.services.soft_delete_service import (
            SoftDeleteService,
            OriginalIdentifierUnavailableError,
        )

        with app_with_db.test_request_context("/"):
            g.m8flow_tenant_id = "test-tenant"
            user = MagicMock()
            user.username = "admin@test.com"

            deletion = SoftDeleteService.soft_delete_process_model("group1/model1", user=user)

            _write_minimal_process_model(os.path.join(bpmn_root, "group1", "model1"), "Reused Model")

            with pytest.raises(OriginalIdentifierUnavailableError):
                SoftDeleteService.restore_process_model(deletion.id, user=user)

    @patch("spiffworkflow_backend.routes.process_api_blueprint._commit_and_push_to_git")
    def test_restore_with_new_identifier_succeeds(self, mock_git, app_with_db, bpmn_root):
        from spiffworkflow_backend.models.db import db
        from m8flow_backend.services.soft_delete_service import SoftDeleteService

        with app_with_db.test_request_context("/"):
            g.m8flow_tenant_id = "test-tenant"
            user = MagicMock()
            user.username = "admin@test.com"

            deletion = SoftDeleteService.soft_delete_process_model("group1/model1", user=user)

            _write_minimal_process_model(os.path.join(bpmn_root, "group1", "model1"), "Reused Model")

            process_model = SoftDeleteService.restore_process_model(
                deletion.id, new_identifier="group1/model1_restored", user=user
            )
            assert process_model is not None
            restored_path = os.path.join(bpmn_root, "group1", "model1_restored")
            assert os.path.exists(restored_path)


class TestPurge:
    @patch("spiffworkflow_backend.routes.process_api_blueprint._commit_and_push_to_git")
    def test_purge_single_process_model(self, mock_git, app_with_db, bpmn_root):
        from spiffworkflow_backend.models.db import db
        from m8flow_backend.services.soft_delete_service import SoftDeleteService
        from m8flow_backend.models.process_model_deletion import ProcessModelDeletionModel, DeletionStatus

        with app_with_db.test_request_context("/"):
            g.m8flow_tenant_id = "test-tenant"
            user = MagicMock()
            user.username = "admin@test.com"

            deletion = SoftDeleteService.soft_delete_process_model("group1/model1", user=user)
            deleted_path = FileSystemService.full_path_from_id(deletion.deleted_identifier)
            assert os.path.exists(deleted_path)

            result = SoftDeleteService.purge_single_process_model(deletion.id, user=user)
            assert result.status == DeletionStatus.PURGED.value
            assert not os.path.exists(deleted_path)

    @patch("spiffworkflow_backend.routes.process_api_blueprint._commit_and_push_to_git")
    def test_purge_expired_removes_old_items(self, mock_git, app_with_db, bpmn_root):
        from spiffworkflow_backend.models.db import db
        from m8flow_backend.services.soft_delete_service import SoftDeleteService
        from m8flow_backend.models.process_model_deletion import ProcessModelDeletionModel, DeletionStatus
        from m8flow_backend.models.m8flow_tenant import M8flowTenantModel

        with app_with_db.test_request_context("/"):
            g.m8flow_tenant_id = "test-tenant"
            user = MagicMock()
            user.username = "admin@test.com"

            tenant = M8flowTenantModel(id="test-tenant", name="Test", slug="test")
            db.session.add(tenant)
            db.session.commit()

            deletion = SoftDeleteService.soft_delete_process_model("group1/model1", user=user)

            deletion_row = db.session.get(ProcessModelDeletionModel, deletion.id)
            deletion_row.deleted_at_in_seconds = int(time.time()) - 100000
            db.session.commit()

            summary = SoftDeleteService.purge_expired(retention_seconds=86400, dry_run=False)
            assert summary["process_models_purged"] == 1

            row = db.session.get(ProcessModelDeletionModel, deletion.id)
            assert row.status == DeletionStatus.PURGED.value


class TestPatchedDeleteFallsBackToSoftDelete:
    def test_patched_process_model_delete_falls_to_soft_delete(self, app_with_db, bpmn_root):
        """When upstream raises ProcessModelWithInstancesNotDeletableError,
        the patched delete should fall back to soft-delete."""
        from m8flow_backend.services.soft_delete_service import SoftDeleteService

        with app_with_db.test_request_context("/"):
            g.m8flow_tenant_id = "test-tenant"
            g.user = MagicMock()
            g.user.username = "admin@test.com"

            with patch.object(
                SoftDeleteService,
                "soft_delete_process_model",
                return_value=MagicMock(),
            ) as mock_sd:
                from m8flow_backend.services.process_model_service_patch import (
                    ProcessModelServicePatches,
                )

                original_delete = MagicMock(side_effect=ProcessModelWithInstancesNotDeletableError("has instances"))

                with patch(
                    "m8flow_backend.services.process_model_service_patch.original_process_model_delete",
                    original_delete,
                ):
                    with patch(
                        "m8flow_backend.services.process_model_service_patch.is_super_admin_request",
                        return_value=False,
                    ):
                        ProcessModelServicePatches.patched_process_model_delete("group1/model1")
                        mock_sd.assert_called_once_with("group1/model1", user=g.user)


class TestListDeleted:
    @patch("spiffworkflow_backend.routes.process_api_blueprint._commit_and_push_to_git")
    def test_list_returns_soft_deleted_items(self, mock_git, app_with_db, bpmn_root):
        from spiffworkflow_backend.models.db import db
        from m8flow_backend.services.soft_delete_service import SoftDeleteService
        from m8flow_backend.models.process_model_deletion import DeletionStatus

        with app_with_db.test_request_context("/"):
            g.m8flow_tenant_id = "test-tenant"
            user = MagicMock()
            user.username = "admin@test.com"

            SoftDeleteService.soft_delete_process_model("group1/model1", user=user)
            SoftDeleteService.soft_delete_process_model("group1/model2", user=user)

            items, pagination = SoftDeleteService.list_deleted_process_models(tenant_id="test-tenant")
            assert len(items) == 2
            assert pagination["total"] == 2

    @patch("spiffworkflow_backend.routes.process_api_blueprint._commit_and_push_to_git")
    def test_list_excludes_restored_items(self, mock_git, app_with_db, bpmn_root):
        from spiffworkflow_backend.models.db import db
        from m8flow_backend.services.soft_delete_service import SoftDeleteService

        with app_with_db.test_request_context("/"):
            g.m8flow_tenant_id = "test-tenant"
            user = MagicMock()
            user.username = "admin@test.com"

            deletion = SoftDeleteService.soft_delete_process_model("group1/model1", user=user)
            SoftDeleteService.restore_process_model(deletion.id, user=user)

            items, pagination = SoftDeleteService.list_deleted_process_models(tenant_id="test-tenant")
            assert len(items) == 0
