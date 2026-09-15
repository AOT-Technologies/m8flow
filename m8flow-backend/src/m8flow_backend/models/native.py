from __future__ import annotations

from enum import Enum

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from m8flow_backend.models.host_base import HostBase


class TemplateVisibility(str, Enum):
    private = "PRIVATE"
    tenant = "TENANT"
    public = "PUBLIC"


class SecretModel(HostBase):
    __tablename__ = "secret"
    __table_args__ = (UniqueConstraint("m8f_tenant_id", "key", name="uq_host_secret_tenant_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_user_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    m8f_tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    created_at_in_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at_in_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class PkceCodeVerifierModel(HostBase):
    __tablename__ = "pkce_code_verifier"

    id: Mapped[int] = mapped_column(primary_key=True)
    state: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    code_verifier: Mapped[str] = mapped_column(String(255), nullable=False)
    m8f_tenant_id: Mapped[str | None] = mapped_column(String(255), index=True)
    created_at_in_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class RefreshTokenModel(HostBase):
    __tablename__ = "refresh_token"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    token: Mapped[str] = mapped_column(Text, nullable=False)
    m8f_tenant_id: Mapped[str | None] = mapped_column(String(255), index=True)
    created_at_in_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at_in_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ServiceAccountModel(HostBase):
    __tablename__ = "service_account"
    __table_args__ = (
        UniqueConstraint("m8f_tenant_id", "name", "created_by_user_id", name="service_account_uniq"),
        UniqueConstraint("client_id", name="uq_host_service_account_client_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    secret_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by_user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    m8f_tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    created_at_in_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class TaskDraftDataModel(HostBase):
    __tablename__ = "task_draft_data"
    __table_args__ = (
        UniqueConstraint("process_instance_id", "task_guid", name="uq_host_task_draft"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    process_instance_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    task_guid: Mapped[str] = mapped_column(String(255), nullable=False)
    saved_form_data: Mapped[str | None] = mapped_column(Text)
    m8f_tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    created_at_in_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at_in_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class TaskInstructionsForEndUserModel(HostBase):
    __tablename__ = "task_instructions_for_end_user"

    id: Mapped[int] = mapped_column(primary_key=True)
    process_instance_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    m8f_tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    created_at_in_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class TypeaheadModel(HostBase):
    __tablename__ = "typeahead"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    search_term: Mapped[str] = mapped_column(String(255), nullable=False)
    result: Mapped[str] = mapped_column(Text, nullable=False)
    m8f_tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)


class ApiLogModel(HostBase):
    __tablename__ = "api_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    path: Mapped[str] = mapped_column(String(255), nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    m8f_tenant_id: Mapped[str | None] = mapped_column(String(255), index=True)
    created_at_in_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ConfigurationModel(HostBase):
    __tablename__ = "configuration"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class ProcessInstanceFileDataModel(HostBase):
    __tablename__ = "process_instance_file_data"

    id: Mapped[int] = mapped_column(primary_key=True)
    process_instance_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    mimetype: Mapped[str | None] = mapped_column(String(255))
    filename: Mapped[str | None] = mapped_column(String(255))
    contents: Mapped[str | None] = mapped_column(Text)
    m8f_tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    created_at_in_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class TemplateModel(HostBase):
    __tablename__ = "m8flow_templates"
    __table_args__ = (
        UniqueConstraint("m8f_tenant_id", "template_key", "version", name="uq_template_key_version_tenant"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    template_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    category: Mapped[str | None] = mapped_column(String(255))
    m8f_tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    visibility: Mapped[str] = mapped_column(String(20), nullable=False, default=TemplateVisibility.private.value)
    files: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str | None] = mapped_column(String(50))
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    modified_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at_in_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at_in_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def is_private(self) -> bool:
        return self.visibility == TemplateVisibility.private.value

    def is_tenant_visible(self) -> bool:
        return self.visibility == TemplateVisibility.tenant.value

    def is_public(self) -> bool:
        return self.visibility == TemplateVisibility.public.value


class ProcessModelTemplateModel(HostBase):
    __tablename__ = "m8flow_process_model_template"
    __table_args__ = (
        UniqueConstraint("m8f_tenant_id", "process_model_identifier", name="uq_process_model_identifier_tenant"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    process_model_identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    source_template_id: Mapped[int] = mapped_column(Integer, ForeignKey("m8flow_templates.id"), nullable=False)
    source_template_key: Mapped[str] = mapped_column(String(255), nullable=False)
    source_template_version: Mapped[str] = mapped_column(String(50), nullable=False)
    source_template_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    m8f_tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    created_at_in_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at_in_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def serialized(self) -> dict:
        return {
            "id": self.id,
            "process_model_identifier": self.process_model_identifier,
            "source_template_id": self.source_template_id,
            "source_template_key": self.source_template_key,
            "source_template_version": self.source_template_version,
            "source_template_name": self.source_template_name,
            "m8f_tenant_id": self.m8f_tenant_id,
            "created_by": self.created_by,
            "created_at_in_seconds": self.created_at_in_seconds,
            "updated_at_in_seconds": self.updated_at_in_seconds,
        }


class M8flowNatsApiKeyModel(HostBase):
    __tablename__ = "m8flow_nats_api_key"

    id: Mapped[int] = mapped_column(primary_key=True)
    key_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    m8f_tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    created_at_in_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
