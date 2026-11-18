"""M8F-703: the Processes list reads each catalog file once.

list_model_rows read process_model.json three times per model, the group's
process_group.json once per model, and parsed every BPMN (and DMN) even for
draft models whose processes the route then dropped.
"""

from __future__ import annotations

import json
from pathlib import Path

from m8flow_backend import catalog

VALID_BPMN = (Path(__file__).resolve().parents[2] / "fixtures" / "invoice_approval_poc.bpmn").read_text(
    encoding="utf-8"
)
DMN = (
    '<definitions xmlns="https://www.omg.org/spec/DMN/20191111/MODEL/" id="d" name="d">'
    '<decision id="pick_approver" name="Pick approver"/></definitions>'
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _seed_catalog(tmp_path, monkeypatch) -> None:
    """finance/ holds a published model (with a DMN), a draft with broken BPMN,
    and a model with no status (reads as published); ops/ holds one more."""
    root = tmp_path / "bpmn" / "t1"
    _write(root / "finance" / "process_group.json", json.dumps({"display_name": "Finance Team"}))
    _write(root / "finance" / "approve" / "approve.bpmn", VALID_BPMN)
    _write(root / "finance" / "approve" / "rules.dmn", DMN)
    _write(
        root / "finance" / "approve" / "process_model.json",
        json.dumps({"display_name": "Approve Invoice", "status": "published"}),
    )
    _write(root / "finance" / "draft" / "draft.bpmn", "<not-xml")
    _write(
        root / "finance" / "draft" / "process_model.json",
        json.dumps({"display_name": "Draft Invoice", "status": "draft"}),
    )
    _write(root / "finance" / "legacy" / "legacy.bpmn", VALID_BPMN)
    _write(root / "finance" / "legacy" / "process_model.json", json.dumps({}))
    _write(root / "ops" / "restart" / "restart.bpmn", VALID_BPMN)
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path / "bpmn"))


def test_list_rows_payload_is_unchanged(tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch)

    rows = catalog.list_model_rows(tenant_id="t1")

    simple = [{"id": "simple_approval", "file_name": None}]

    def processes(file_name: str) -> list[dict[str, str]]:
        return [{**item, "file_name": file_name} for item in simple]

    def versions(model_id: str, status: str) -> dict:
        # Process versioning's own fields, unchanged by this listing's reads.
        return catalog.versioned.version_fields("t1", model_id, status)

    assert rows == [
        {
            "id": "finance/approve",
            "tenant_id": "t1",
            "bpmn_processes": processes("approve.bpmn"),
            "display_name": "Approve Invoice",
            "group_id": "finance",
            "group_display_name": "Finance Team",
            "status": "published",
            **versions("finance/approve", "published"),
        },
        {
            "id": "finance/draft",
            "tenant_id": "t1",
            "bpmn_processes": [],
            "display_name": "Draft Invoice",
            "group_id": "finance",
            "group_display_name": "Finance Team",
            "status": "draft",
            **versions("finance/draft", "draft"),
        },
        {
            "id": "finance/legacy",
            "tenant_id": "t1",
            "bpmn_processes": processes("legacy.bpmn"),
            "display_name": "legacy",
            "group_id": "finance",
            "group_display_name": "Finance Team",
            "status": "published",
            **versions("finance/legacy", "published"),
        },
        {
            "id": "ops/restart",
            "tenant_id": "t1",
            "bpmn_processes": processes("restart.bpmn"),
            "display_name": "restart",
            "group_id": "ops",
            "group_display_name": "ops",
            "status": "published",
            **versions("ops/restart", "published"),
        },
    ]


def test_list_rows_parse_only_published_bpmn_and_no_dmn(tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch)
    parsed: list[str] = []
    real_fromstring = catalog.SafeElementTree.fromstring

    def counting_fromstring(source, *args, **kwargs):
        text = source.decode("utf-8", "replace") if isinstance(source, bytes) else source
        parsed.append("dmn" if "DMN/" in text else "bpmn")
        return real_fromstring(source, *args, **kwargs)

    monkeypatch.setattr(catalog.SafeElementTree, "fromstring", counting_fromstring)

    rows = catalog.list_model_rows(tenant_id="t1")

    assert len(rows) == 4
    # approve, legacy, restart: one BPMN each. Not the draft, never the DMN.
    assert parsed == ["bpmn", "bpmn", "bpmn"]


def test_list_rows_read_status_name_and_group_once(tmp_path, monkeypatch):
    """Status and display name share one process_model.json read per model, and each
    group's process_group.json is read once. Process versioning's own reads (version
    fields, the legacy BPMN snapshot) are stubbed out: they are not this listing's."""
    _seed_catalog(tmp_path, monkeypatch)
    monkeypatch.setattr(catalog.versioned, "version_fields", lambda *_args: {})
    monkeypatch.setattr(catalog, "_bpmn_processes_for_model", lambda **_kwargs: [])
    reads: list[str] = []
    real_read_json_file = catalog.read_json_file

    def counting_read_json_file(path):
        reads.append(f"{path.parent.name}/{path.name}")
        return real_read_json_file(path)

    monkeypatch.setattr(catalog, "read_json_file", counting_read_json_file)

    catalog.list_model_rows(tenant_id="t1")

    assert sorted(reads) == [
        "approve/process_model.json",
        "draft/process_model.json",
        "finance/process_group.json",
        "legacy/process_model.json",
        "ops/process_group.json",
        "restart/process_model.json",
    ]
