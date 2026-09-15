from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from m8flow_backend.models.native import ProcessModelTemplateModel, TemplateModel, TemplateVisibility


def _template(**overrides) -> TemplateModel:
    row = TemplateModel(
        template_key="approval",
        version="V1",
        name="Approval",
        m8f_tenant_id="t1",
        visibility=TemplateVisibility.private.value,
        files=[{"file_type": "bpmn", "file_name": "diagram.bpmn"}],
        created_by="editor",
        modified_by="editor",
    )
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


def test_visibility_helpers():
    assert _template(visibility=TemplateVisibility.public.value).is_public() is True
    assert _template(visibility=TemplateVisibility.public.value).is_private() is False
    assert _template(visibility=TemplateVisibility.tenant.value).is_tenant_visible() is True
    assert _template(visibility=TemplateVisibility.private.value).is_private() is True
    assert TemplateVisibility.public.value == "PUBLIC"


def test_provenance_serialized_keys(db_session):
    template = _template()
    db_session.add(template)
    db_session.flush()
    provenance = ProcessModelTemplateModel(
        process_model_identifier="finance/from-template",
        source_template_id=template.id,
        source_template_key=template.template_key,
        source_template_version=template.version,
        source_template_name=template.name,
        created_by="editor",
        m8f_tenant_id="t1",
    )
    db_session.add(provenance)
    db_session.flush()
    payload = provenance.serialized()
    assert payload == {
        "id": provenance.id,
        "process_model_identifier": "finance/from-template",
        "source_template_id": template.id,
        "source_template_key": "approval",
        "source_template_version": "V1",
        "source_template_name": "Approval",
        "m8f_tenant_id": "t1",
        "created_by": "editor",
        "created_at_in_seconds": provenance.created_at_in_seconds,
        "updated_at_in_seconds": provenance.updated_at_in_seconds,
    }


def test_template_key_version_unique_per_tenant(db_session):
    db_session.add(_template())
    db_session.flush()
    db_session.add(_template())
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_provenance_unique_per_tenant_process_model(db_session):
    template = _template()
    db_session.add(template)
    db_session.flush()
    kwargs = dict(
        process_model_identifier="finance/from-template",
        source_template_id=template.id,
        source_template_key=template.template_key,
        source_template_version=template.version,
        source_template_name=template.name,
        created_by="editor",
        m8f_tenant_id="t1",
    )
    db_session.add(ProcessModelTemplateModel(**kwargs))
    db_session.flush()
    db_session.add(ProcessModelTemplateModel(**kwargs))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()
