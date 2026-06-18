"""Playwright API route mocking helpers for browser tests.

Uses ``page.route()`` to intercept backend API calls and return
deterministic JSON responses, removing the dependency on seeded data.

Covers templates, tenants, and process groups.
"""
from __future__ import annotations

import copy
import json
import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from playwright.sync_api import Page, Route

# ===================================================================
# Template mock data -- m8flow tenant
# ===================================================================

MOCK_TEMPLATE_PRIVATE: dict[str, Any] = {
    "id": 1,
    "templateKey": "test-template-private",
    "version": "V1",
    "name": "Private Test Template",
    "description": "A private test template",
    "tags": ["test"],
    "category": "Testing",
    "tenantId": "m8flow",
    "visibility": "PRIVATE",
    "files": [
        {"fileType": "bpmn", "fileName": "process.bpmn"},
        {"fileType": "json", "fileName": "form.json"},
    ],
    "isPublished": False,
    "status": "DRAFT",
    "createdAtInSeconds": 1700000000,
    "createdBy": "admin",
    "updatedAtInSeconds": 1700000000,
    "modifiedBy": "admin",
}

MOCK_TEMPLATE_TENANT: dict[str, Any] = {
    "id": 2,
    "templateKey": "test-template-tenant",
    "version": "V1",
    "name": "Tenant Test Template",
    "description": "A tenant-wide test template",
    "tags": ["shared"],
    "category": "Shared",
    "tenantId": "m8flow",
    "visibility": "TENANT",
    "files": [{"fileType": "bpmn", "fileName": "workflow.bpmn"}],
    "isPublished": False,
    "status": "DRAFT",
    "createdAtInSeconds": 1700001000,
    "createdBy": "admin",
    "updatedAtInSeconds": 1700001000,
    "modifiedBy": "admin",
}

MOCK_TEMPLATE_PUBLIC: dict[str, Any] = {
    "id": 3,
    "templateKey": "test-template-public",
    "version": "V1",
    "name": "Public Test Template",
    "description": "A public test template visible to all",
    "tags": ["public"],
    "category": "Public",
    "tenantId": "m8flow",
    "visibility": "PUBLIC",
    "files": [{"fileType": "bpmn", "fileName": "public-process.bpmn"}],
    "isPublished": False,
    "status": "DRAFT",
    "createdAtInSeconds": 1700002000,
    "createdBy": "admin",
    "updatedAtInSeconds": 1700002000,
    "modifiedBy": "admin",
}

MOCK_TEMPLATE_PUBLISHED: dict[str, Any] = {
    "id": 4,
    "templateKey": "test-template-published",
    "version": "V1",
    "name": "Published Test Template",
    "description": "A published template",
    "tags": ["released"],
    "category": "Production",
    "tenantId": "m8flow",
    "visibility": "TENANT",
    "files": [
        {"fileType": "bpmn", "fileName": "released.bpmn"},
        {"fileType": "json", "fileName": "form.json"},
    ],
    "isPublished": True,
    "status": "PUBLISHED",
    "createdAtInSeconds": 1700003000,
    "createdBy": "admin",
    "updatedAtInSeconds": 1700003000,
    "modifiedBy": "admin",
}

MOCK_TEMPLATE_V2: dict[str, Any] = {
    "id": 5,
    "templateKey": "test-template-published",
    "version": "V2",
    "name": "Published Test Template",
    "description": "Draft of V2",
    "tags": ["released"],
    "category": "Production",
    "tenantId": "m8flow",
    "visibility": "TENANT",
    "files": [{"fileType": "bpmn", "fileName": "released.bpmn"}],
    "isPublished": False,
    "status": "DRAFT",
    "createdAtInSeconds": 1700004000,
    "createdBy": "admin",
    "updatedAtInSeconds": 1700004000,
    "modifiedBy": "admin",
}

ALL_MOCK_TEMPLATES: list[dict[str, Any]] = [
    MOCK_TEMPLATE_PRIVATE,
    MOCK_TEMPLATE_TENANT,
    MOCK_TEMPLATE_PUBLIC,
    MOCK_TEMPLATE_PUBLISHED,
]

# ===================================================================
# Template mock data -- acme tenant (cross-tenant isolation)
# ===================================================================

MOCK_ACME_TEMPLATE_PRIVATE: dict[str, Any] = {
    "id": 101,
    "templateKey": "acme-template-private",
    "version": "V1",
    "name": "Acme Private Template",
    "description": "Private template owned by Acme Corp",
    "tags": ["acme", "internal"],
    "category": "Internal",
    "tenantId": "acme",
    "visibility": "PRIVATE",
    "files": [{"fileType": "bpmn", "fileName": "acme-private.bpmn"}],
    "isPublished": False,
    "status": "DRAFT",
    "createdAtInSeconds": 1700100000,
    "createdBy": "acme-admin",
    "updatedAtInSeconds": 1700100000,
    "modifiedBy": "acme-admin",
}

MOCK_ACME_TEMPLATE_TENANT: dict[str, Any] = {
    "id": 102,
    "templateKey": "acme-template-tenant",
    "version": "V1",
    "name": "Acme Tenant Template",
    "description": "Tenant-wide template shared within Acme Corp",
    "tags": ["acme", "shared"],
    "category": "Acme Shared",
    "tenantId": "acme",
    "visibility": "TENANT",
    "files": [{"fileType": "bpmn", "fileName": "acme-shared.bpmn"}],
    "isPublished": False,
    "status": "DRAFT",
    "createdAtInSeconds": 1700101000,
    "createdBy": "acme-admin",
    "updatedAtInSeconds": 1700101000,
    "modifiedBy": "acme-admin",
}

MOCK_ACME_TEMPLATE_PUBLIC: dict[str, Any] = {
    "id": 103,
    "templateKey": "acme-template-public",
    "version": "V1",
    "name": "Acme Public Template",
    "description": "Public template from Acme Corp visible to all tenants",
    "tags": ["acme", "public"],
    "category": "Acme Public",
    "tenantId": "acme",
    "visibility": "PUBLIC",
    "files": [{"fileType": "bpmn", "fileName": "acme-public.bpmn"}],
    "isPublished": True,
    "status": "PUBLISHED",
    "createdAtInSeconds": 1700102000,
    "createdBy": "acme-admin",
    "updatedAtInSeconds": 1700102000,
    "modifiedBy": "acme-admin",
}

ALL_ACME_TEMPLATES: list[dict[str, Any]] = [
    MOCK_ACME_TEMPLATE_PRIVATE,
    MOCK_ACME_TEMPLATE_TENANT,
    MOCK_ACME_TEMPLATE_PUBLIC,
]

# What an m8flow user would see: own templates + PUBLIC from acme
M8FLOW_USER_VISIBLE_TEMPLATES: list[dict[str, Any]] = [
    MOCK_TEMPLATE_PRIVATE,
    MOCK_TEMPLATE_TENANT,
    MOCK_TEMPLATE_PUBLIC,
    MOCK_TEMPLATE_PUBLISHED,
    MOCK_ACME_TEMPLATE_PUBLIC,
]

# ===================================================================
# Tenant mock data
# ===================================================================

MOCK_TENANT_M8FLOW: dict[str, Any] = {
    "id": "t-m8flow-001",
    "name": "M8Flow",
    "slug": "m8flow",
    "status": "ACTIVE",
    "createdBy": "super-admin",
    "modifiedBy": "super-admin",
    "createdAtInSeconds": 1699000000,
    "updatedAtInSeconds": 1699000000,
}

MOCK_TENANT_ACME: dict[str, Any] = {
    "id": "t-acme-001",
    "name": "Acme Corp",
    "slug": "acme",
    "status": "ACTIVE",
    "createdBy": "super-admin",
    "modifiedBy": "super-admin",
    "createdAtInSeconds": 1699500000,
    "updatedAtInSeconds": 1699500000,
}

MOCK_TENANT_INACTIVE: dict[str, Any] = {
    "id": "t-old-001",
    "name": "Old Company",
    "slug": "old-company",
    "status": "INACTIVE",
    "createdBy": "super-admin",
    "modifiedBy": "super-admin",
    "createdAtInSeconds": 1698000000,
    "updatedAtInSeconds": 1698500000,
}

ALL_MOCK_TENANTS: list[dict[str, Any]] = [
    MOCK_TENANT_M8FLOW,
    MOCK_TENANT_ACME,
    MOCK_TENANT_INACTIVE,
]

# Tenant ids -- the global tenant selector keys off ``tenant.id`` and per-page
# data is filtered by ``tenantId == selectedTenantId``, so every cross-tenant
# dataset below uses these ids as its ``tenantId``.
M8FLOW_TENANT_ID: str = MOCK_TENANT_M8FLOW["id"]
ACME_TENANT_ID: str = MOCK_TENANT_ACME["id"]
OLD_TENANT_ID: str = MOCK_TENANT_INACTIVE["id"]

# The two active tenants -- the common base for super-admin filter/isolation tests.
SUPER_ADMIN_ACTIVE_TENANTS: list[dict[str, Any]] = [MOCK_TENANT_M8FLOW, MOCK_TENANT_ACME]

# ===================================================================
# Process group mock data
# ===================================================================

MOCK_PROCESS_GROUP: dict[str, Any] = {
    "id": "test-group",
    "display_name": "Test Process Group",
    "description": "A test process group for E2E tests",
    "process_models": [],
    "process_groups": [],
}

MOCK_PROCESS_GROUP_HR: dict[str, Any] = {
    "id": "hr-processes",
    "display_name": "HR Processes",
    "description": "Human Resources process group",
    "process_models": [],
    "process_groups": [],
}

ALL_MOCK_PROCESS_GROUPS: list[dict[str, Any]] = [
    MOCK_PROCESS_GROUP,
    MOCK_PROCESS_GROUP_HR,
]

# ===================================================================
# Pagination helper
# ===================================================================

DEFAULT_PAGINATION: dict[str, Any] = {
    "count": 0,
    "page": 1,
    "pages": 1,
    "per_page": 10,
    "total": 0,
}


def _make_pagination(items: list[Any]) -> dict[str, Any]:
    return {
        **DEFAULT_PAGINATION,
        "count": len(items),
        "total": len(items),
    }


# ===================================================================
# Internal helpers
# ===================================================================

_TEMPLATE_DETAIL_RE = re.compile(r"/v1\.0/m8flow/templates/(\d+)(?:\?|$)")
_TENANT_DETAIL_RE = re.compile(r"/v1\.0/m8flow/tenants/([^/?]+)(?:\?|$)")


def _json_response(route: Route, body: Any, status: int = 200) -> None:
    route.fulfill(
        status=status,
        content_type="application/json",
        body=json.dumps(body),
    )


def _filter_templates(
    templates: list[dict[str, Any]], url: str
) -> list[dict[str, Any]]:
    """Apply query-param filters that the gallery page sends."""
    qs = parse_qs(urlparse(url).query)
    result = list(templates)

    if "visibility" in qs:
        vis = qs["visibility"][0].upper()
        result = [t for t in result if t["visibility"] == vis]

    if "search" in qs:
        term = qs["search"][0].lower()
        result = [
            t
            for t in result
            if term in t["name"].lower()
            or term in (t.get("description") or "").lower()
        ]

    if "category" in qs:
        cat = qs["category"][0]
        result = [t for t in result if t.get("category") == cat]

    if "template_key" in qs:
        key = qs["template_key"][0]
        result = [t for t in result if t["templateKey"] == key]

    # Super-admin tenant filter: the gallery sends ``tenantId`` when a tenant is
    # selected in the global tenant filter.
    if "tenantId" in qs:
        tid = qs["tenantId"][0]
        result = [t for t in result if t.get("tenantId") == tid]

    if "published_only" in qs and qs["published_only"][0].lower() == "true":
        result = [t for t in result if t.get("isPublished")]

    # Gallery default sends latest_only=true; collapse multiple versions of the same key.
    if (
        "template_key" not in qs
        and "latest_only" in qs
        and str(qs["latest_only"][0]).lower() == "true"
    ):
        best: dict[str, dict[str, Any]] = {}
        for t in result:
            key = str(t.get("templateKey", ""))
            if not key:
                continue
            prev = best.get(key)
            if prev is None or int(t.get("id", 0)) > int(prev.get("id", 0)):
                best[key] = t
        result = list(best.values())

    return result


def _paginate_template_results(items: list[dict[str, Any]], url: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Slice *items* using ``page`` / ``per_page`` query params and build pagination metadata."""
    qs = parse_qs(urlparse(url).query)
    page_num = int(qs.get("page", ["1"])[0] or 1)
    per_page = int(qs.get("per_page", ["10"])[0] or 10)
    total = len(items)
    per_page = max(1, per_page)
    pages = max(1, (total + per_page - 1) // per_page)
    page_num = max(1, min(page_num, pages))
    start = (page_num - 1) * per_page
    slice_ = items[start : start + per_page]
    return slice_, {
        "count": len(slice_),
        "page": page_num,
        "pages": pages,
        "per_page": per_page,
        "total": total,
    }


def _filter_tenants(
    tenants: list[dict[str, Any]], url: str
) -> list[dict[str, Any]]:
    """Apply query-param / search filtering for the tenant list."""
    qs = parse_qs(urlparse(url).query)
    result = list(tenants)

    if "search" in qs:
        term = qs["search"][0].lower()
        result = [
            t
            for t in result
            if term in t["name"].lower() or term in t["slug"].lower()
        ]

    return result


# ===================================================================
# Template mocking
# ===================================================================


def mock_template_gallery(
    page: Page,
    templates: list[dict[str, Any]] | None = None,
) -> None:
    """Intercept GET /v1.0/m8flow/templates (list endpoint) only."""
    source = templates if templates is not None else ALL_MOCK_TEMPLATES

    def _handle_list(route: Route) -> None:
        url = route.request.url
        if route.request.method != "GET":
            route.fallback()
            return
        if _TEMPLATE_DETAIL_RE.search(url):
            route.fallback()
            return
        # More specific routes (files, export, import, etc.) register after this handler
        # and rely on ``fallback`` when these path markers are present.
        if "/files/" in url or "/export" in url or "/import" in url or "create-process-model" in url:
            route.fallback()
            return

        filtered = _filter_templates(source, url)
        page_slice, pagination = _paginate_template_results(filtered, url)
        _json_response(route, {
            "results": page_slice,
            "pagination": pagination,
        })

    page.route("**/v1.0/m8flow/templates*", _handle_list)


def mock_template_detail(
    page: Page,
    template: dict[str, Any] | None = None,
    all_versions: list[dict[str, Any]] | None = None,
) -> None:
    """Intercept GET/PUT /v1.0/m8flow/templates/<id> (detail endpoint)."""
    tpl = template if template is not None else MOCK_TEMPLATE_PRIVATE
    versions = all_versions if all_versions is not None else [tpl]
    by_id: dict[int, dict[str, Any]] = {}
    for v in versions:
        by_id[int(v["id"])] = copy.deepcopy(v)
    if int(tpl["id"]) not in by_id:
        by_id[int(tpl["id"])] = copy.deepcopy(tpl)

    def _handle_detail(route: Route) -> None:
        url = route.request.url
        method = route.request.method

        m = _TEMPLATE_DETAIL_RE.search(url)
        if not m:
            route.fallback()
            return

        tid = int(m.group(1))
        current = copy.deepcopy(by_id.get(tid, tpl))

        if method == "GET":
            if "template_key" in url:
                _json_response(route, {"results": versions})
            else:
                _json_response(route, current)
        elif method == "PUT":
            body = route.request.post_data
            updates = json.loads(body) if body else {}
            updated = {**current, **updates}
            if updates.get("is_published"):
                updated["isPublished"] = True
                updated["status"] = "PUBLISHED"
            by_id[tid] = copy.deepcopy(updated)
            _json_response(route, updated)
        else:
            route.fallback()

    page.route("**/v1.0/m8flow/templates/*", _handle_detail)


def mock_template_import_api(
    page: Page,
    response_template: dict[str, Any] | None = None,
) -> None:
    """Intercept POST /v1.0/m8flow/templates/import (zip import)."""

    created = copy.deepcopy(response_template or MOCK_TEMPLATE_PRIVATE)
    created["id"] = 88888
    created["templateKey"] = "imported-from-browser-test"
    created["name"] = "Imported From Browser Test"
    created["version"] = "V1"
    created["visibility"] = "PRIVATE"
    created["isPublished"] = False
    created["status"] = "DRAFT"

    def _handle(route: Route) -> None:
        if route.request.method != "POST":
            route.fallback()
            return
        if "/templates/import" not in route.request.url:
            route.fallback()
            return
        _json_response(route, created)

    page.route("**/v1.0/m8flow/templates/import*", _handle)


def mock_template_api(
    page: Page,
    templates: list[dict[str, Any]] | None = None,
    template_detail: dict[str, Any] | None = None,
    all_versions: list[dict[str, Any]] | None = None,
) -> None:
    """Set up all template API route interceptors at once."""
    mock_template_detail(page, template_detail, all_versions)
    mock_template_gallery(page, templates)
    mock_template_import_api(page)


# ===================================================================
# Tenant mocking
# ===================================================================


def mock_tenants_api(
    page: Page,
    tenants: list[dict[str, Any]] | None = None,
) -> None:
    """Intercept GET/PUT/DELETE /v1.0/m8flow/tenants endpoints."""
    source = tenants if tenants is not None else ALL_MOCK_TENANTS
    tenant_map = {t["id"]: copy.deepcopy(t) for t in source}

    def _handle_tenant_detail(route: Route) -> None:
        url = route.request.url
        method = route.request.method

        m = _TENANT_DETAIL_RE.search(url)
        if not m:
            route.fallback()
            return

        tenant_id = m.group(1)
        tenant = tenant_map.get(tenant_id)

        if method == "GET":
            if tenant:
                _json_response(route, tenant)
            else:
                _json_response(route, {"message": "Tenant not found"}, status=404)
        elif method == "PUT":
            if not tenant:
                _json_response(route, {"message": "Tenant not found"}, status=404)
                return
            body = route.request.post_data
            updates = json.loads(body) if body else {}
            tenant.update(updates)
            _json_response(route, tenant)
        elif method == "DELETE":
            if tenant:
                tenant["status"] = "DELETED"
                _json_response(route, None, status=204)
            else:
                _json_response(route, {"message": "Tenant not found"}, status=404)
        else:
            route.fallback()

    def _handle_tenant_list(route: Route) -> None:
        url = route.request.url
        if _TENANT_DETAIL_RE.search(url):
            route.fallback()
            return

        active = [t for t in tenant_map.values() if t["status"] != "DELETED"]
        filtered = _filter_tenants(active, url)
        _json_response(route, filtered)

    page.route("**/v1.0/m8flow/tenants/*", _handle_tenant_detail)
    page.route("**/v1.0/m8flow/tenants*", _handle_tenant_list)


# ===================================================================
# Process group mocking
# ===================================================================


def mock_process_groups_api(
    page: Page,
    groups: list[dict[str, Any]] | None = None,
) -> None:
    """Intercept /process-groups API calls (not full-page document navigations).

    GET returns a paginated list. POST appends a synthetic group to an in-memory
    copy of ``groups`` and returns that object so create flows stay consistent
    on subsequent GETs (browser tests should not depend on a writable backend).
    """
    state: list[dict[str, Any]] = copy.deepcopy(
        groups if groups is not None else ALL_MOCK_PROCESS_GROUPS
    )

    def _slug_from_display(name: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        return slug or "process-group"

    def _handle_groups(route: Route) -> None:
        if route.request.resource_type == "document":
            route.fallback()
            return
        req = route.request
        if req.method == "POST":
            body: dict[str, Any] = {}
            if req.post_data:
                try:
                    body = json.loads(req.post_data)
                except json.JSONDecodeError:
                    body = {}
            display_name = (
                body.get("display_name")
                or body.get("displayName")
                or "Untitled Group"
            )
            raw_id = (
                body.get("id")
                or body.get("identifier")
                or _slug_from_display(str(display_name))
            )
            new_group: dict[str, Any] = {
                "id": str(raw_id),
                "display_name": str(display_name),
                "description": str(body.get("description") or ""),
                "process_models": [],
                "process_groups": [],
            }
            state.append(new_group)
            _json_response(route, new_group)
            return
        # Super-admin tenant filter: ``useProcessGroups`` appends ``tenantId``
        # when a tenant is selected in the global tenant filter.
        visible = state
        qs = parse_qs(urlparse(req.url).query)
        if "tenantId" in qs:
            tid = qs["tenantId"][0]
            visible = [g for g in state if g.get("tenantId") == tid]
        _json_response(route, {
            "results": visible,
            "pagination": _make_pagination(visible),
        })

    page.route("**/process-groups*", _handle_groups)


# ===================================================================
# Permissions mocking
# ===================================================================

_SAMPLE_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" xmlns:spiffworkflow="http://spiffworkflow.org/bpmn/schema/1.0/core" xmlns:di="http://www.omg.org/spec/DD/20100524/DI" id="Definitions_96f6665" targetNamespace="http://bpmn.io/schema/bpmn" exporter="Camunda Modeler" exporterVersion="3.0.0-dev">
  <bpmn:process id="Process_sample_process_automation_0m6iyy5" isExecutable="true">
    <bpmn:startEvent id="StartEvent_1">
      <bpmn:outgoing>Flow_17db3yp</bpmn:outgoing>
    </bpmn:startEvent>
    <bpmn:sequenceFlow id="Flow_17db3yp" sourceRef="StartEvent_1" targetRef="Activity_0qpzdpu" />
    <bpmn:endEvent id="EndEvent_1">
      <bpmn:incoming>Flow_12pkbxb</bpmn:incoming>
    </bpmn:endEvent>
    <bpmn:sequenceFlow id="Flow_12pkbxb" sourceRef="Activity_0qpzdpu" targetRef="EndEvent_1" />
    <bpmn:manualTask id="Activity_0qpzdpu" name="Example manual task">
      <bpmn:extensionElements>
        <spiffworkflow:instructionsForEndUser>This is an example **Manual Task**. A **Manual Task** is designed to allow someone to complete a task outside of the system and then report back that it is complete. You can click the *Continue* button to proceed. When you are done running this process, you can edit the **Process Model** to include a:

 * **Script Task** - write a short snippet of python code to update some data
 *  **User Task** - generate a form that collects information from a user
 * **Service Task** - communicate with an external API to fetch or update some data.

You can also change the text you are reading here by updating the *Instructions* on this example manual task.</spiffworkflow:instructionsForEndUser>
      </bpmn:extensionElements>
      <bpmn:incoming>Flow_17db3yp</bpmn:incoming>
      <bpmn:outgoing>Flow_12pkbxb</bpmn:outgoing>
    </bpmn:manualTask>
  </bpmn:process>
  <bpmndi:BPMNDiagram id="BPMNDiagram_1">
    <bpmndi:BPMNPlane id="BPMNPlane_1" bpmnElement="Process_sample_process_automation_0m6iyy5">
      <bpmndi:BPMNShape id="_BPMNShape_StartEvent_2" bpmnElement="StartEvent_1">
        <dc:Bounds x="179" y="159" width="36" height="36" />
      </bpmndi:BPMNShape>
      <bpmndi:BPMNShape id="Event_14za570_di" bpmnElement="EndEvent_1">
        <dc:Bounds x="432" y="159" width="36" height="36" />
      </bpmndi:BPMNShape>
      <bpmndi:BPMNShape id="Activity_0zqotmb_di" bpmnElement="Activity_0qpzdpu">
        <dc:Bounds x="270" y="137" width="100" height="80" />
        <bpmndi:BPMNLabel />
      </bpmndi:BPMNShape>
      <bpmndi:BPMNEdge id="Flow_17db3yp_di" bpmnElement="Flow_17db3yp">
        <di:waypoint x="215" y="177" />
        <di:waypoint x="270" y="177" />
      </bpmndi:BPMNEdge>
      <bpmndi:BPMNEdge id="Flow_12pkbxb_di" bpmnElement="Flow_12pkbxb">
        <di:waypoint x="370" y="177" />
        <di:waypoint x="432" y="177" />
      </bpmndi:BPMNEdge>
    </bpmndi:BPMNPlane>
  </bpmndi:BPMNDiagram>
</bpmn:definitions>"""

_SAMPLE_FORM_JSON = json.dumps({
    "title": "Mock Form",
    "components": [{"type": "textfield", "key": "name", "label": "Name"}],
})


def mock_permissions_api(page: Page) -> None:
    """Intercept POST /v1.0/permissions-check and grant all requested permissions."""

    def _handle(route: Route) -> None:
        body = route.request.post_data
        if body:
            data = json.loads(body)
            reqs = data.get("requests_to_check", {})
            results: dict[str, Any] = {}
            for url, methods in reqs.items():
                if isinstance(methods, dict):
                    results[url] = {m: True for m in methods}
                elif isinstance(methods, list):
                    results[url] = {m: True for m in methods}
                else:
                    results[url] = methods
            _json_response(route, {"results": results})
        else:
            _json_response(route, {"results": {}})

    page.route("**/permissions-check*", _handle)


# ===================================================================
# Template export mocking
# ===================================================================

_EMPTY_ZIP = b"PK\x05\x06" + b"\x00" * 18


def mock_template_export_api(page: Page) -> None:
    """Intercept GET /v1.0/m8flow/templates/<id>/export and return a ZIP blob."""

    def _handle(route: Route) -> None:
        route.fulfill(
            status=200,
            content_type="application/zip",
            body=_EMPTY_ZIP,
            headers={
                "Content-Disposition": 'attachment; filename="template-export.zip"',
            },
        )

    page.route("**/v1.0/m8flow/templates/*/export", _handle)


# ===================================================================
# Viewer-specific permissions mocking
# ===================================================================


def mock_viewer_permissions_api(page: Page) -> None:
    """Like mock_permissions_api but denies PUT on template URLs."""

    def _handle(route: Route) -> None:
        body = route.request.post_data
        if body:
            data = json.loads(body)
            reqs = data.get("requests_to_check", {})
            results: dict[str, Any] = {}
            for url, methods in reqs.items():
                if isinstance(methods, dict):
                    results[url] = {
                        m: ("templates" not in url or m != "PUT")
                        for m in methods
                    }
                elif isinstance(methods, list):
                    results[url] = {
                        m: ("templates" not in url or m != "PUT")
                        for m in methods
                    }
                else:
                    results[url] = methods
            _json_response(route, {"results": results})
        else:
            _json_response(route, {"results": {}})

    page.route("**/permissions-check*", _handle)


# ===================================================================
# Template file content mocking
# ===================================================================


def mock_template_files_api(page: Page) -> None:
    """Intercept GET /v1.0/m8flow/templates/<id>/files/<filename>."""

    def _handle_file(route: Route) -> None:
        url = route.request.url
        if url.endswith(".bpmn") or url.endswith(".dmn"):
            route.fulfill(
                status=200,
                content_type="application/xml",
                body=_SAMPLE_BPMN,
            )
        else:
            route.fulfill(
                status=200,
                content_type="application/json",
                body=_SAMPLE_FORM_JSON,
            )

    page.route("**/v1.0/m8flow/templates/*/files/*", _handle_file)


# ===================================================================
# Process model creation mocking
# ===================================================================


def mock_create_process_model_api(page: Page) -> None:
    """Intercept POST /v1.0/m8flow/templates/<id>/create-process-model."""

    def _handle(route: Route) -> None:
        if route.request.method != "POST":
            route.fallback()
            return

        body = json.loads(route.request.post_data or "{}")
        group_id = body.get("process_group_id", "unknown-group")
        model_id = body.get("process_model_id", "unknown-model")
        full_id = f"{group_id}/{model_id}"

        _json_response(route, {
            "process_model": {
                "id": full_id,
                "display_name": body.get("display_name", ""),
            },
            "template_info": {
                "id": 1,
                "process_model_identifier": full_id,
                "source_template_id": 1,
                "source_template_key": "test-template-private",
                "source_template_version": "V1",
                "source_template_name": "Private Test Template",
                "m8f_tenant_id": "m8flow",
                "created_by": "admin",
                "created_at_in_seconds": 1700000000,
                "updated_at_in_seconds": 1700000000,
            },
        })

    page.route("**/v1.0/m8flow/templates/*/create-process-model", _handle)


def mock_process_model_create_with_default_bpmn(page: Page) -> None:
    """Intercept create (POST) + show (GET) + BPMN file (GET) + diagram helpers.

    Simulates backend behaviour: new process model includes ``random_file.bpmn``
    with a minimal executable process (start event). Also stubs ``/validate`` and
    ``/processes`` so the diagram editor can load offline with other mocks.
    """
    models: dict[str, dict[str, Any]] = {}
    bpmn_file_name = "random_file.bpmn"

    def _norm_api_path(url: str) -> str:
        parsed = urlparse(url)
        path = parsed.path
        if path.startswith("/v1.0"):
            path = path[5:]
        return path or "/"

    def _model_key_from_path_segment(segment: str) -> str:
        return unquote(segment).replace(":", "/")

    def _handle_process_models(route: Route) -> None:
        if route.request.resource_type == "document":
            route.fallback()
            return

        url = route.request.url
        path = _norm_api_path(url)
        method = route.request.method

        m_validate = re.match(r"^/process-models/([^/]+)/validate$", path)
        if m_validate and method == "GET":
            _json_response(route, {"valid": True})
            return

        m_file = re.match(r"^/process-models/([^/]+)/files/([^/]+)$", path)
        if m_file and method == "GET":
            model_key = _model_key_from_path_segment(m_file.group(1))
            fname = m_file.group(2)
            if model_key not in models or fname != bpmn_file_name:
                route.fallback()
                return
            _json_response(route, {
                "name": fname,
                "type": "bpmn",
                "file_contents": _SAMPLE_BPMN,
                "file_contents_hash": "mock-file-hash",
                "references": [],
            })
            return

        m_one = re.match(r"^/process-models/([^/?]+)$", path)
        if m_one and method == "GET":
            model_key = _model_key_from_path_segment(m_one.group(1))
            if model_key in models:
                _json_response(route, models[model_key])
                return
            route.fallback()
            return

        m_post = re.match(r"^/process-models/([^/]+)$", path)
        if m_post and method == "POST":
            group_seg = m_post.group(1)
            body = json.loads(route.request.post_data or "{}")
            full_id = body.get("id") or ""
            if not full_id.startswith(f"{group_seg}/"):
                route.fallback()
                return
            payload: dict[str, Any] = {
                "id": full_id,
                "display_name": body.get("display_name", ""),
                "description": body.get("description", ""),
                "primary_file_name": bpmn_file_name,
                "is_executable": True,
                "files": [
                    {
                        "name": bpmn_file_name,
                        "file_contents_hash": "mock-file-hash",
                        "type": "bpmn",
                    }
                ],
            }
            models[full_id] = payload
            _json_response(route, payload)
            return

        route.fallback()

    def _handle_processes(route: Route) -> None:
        if route.request.resource_type == "document":
            route.fallback()
            return
        if route.request.method != "GET":
            route.fallback()
            return
        p = _norm_api_path(route.request.url)
        if p == "/processes" or p.startswith("/processes/callers"):
            _json_response(route, [])
            return
        route.fallback()

    page.route(re.compile(r".*process-models.*"), _handle_process_models)
    page.route("**/v1.0/processes*", _handle_processes)


# ===================================================================
# Combined mocking
# ===================================================================


def mock_all_apis(
    page: Page,
    templates: list[dict[str, Any]] | None = None,
    template_detail: dict[str, Any] | None = None,
    all_versions: list[dict[str, Any]] | None = None,
    tenants: list[dict[str, Any]] | None = None,
    process_groups: list[dict[str, Any]] | None = None,
) -> None:
    """Set up route interceptors for templates, tenants, process groups, and permissions."""
    mock_permissions_api(page)
    mock_template_api(page, templates, template_detail, all_versions)
    mock_template_files_api(page)
    mock_template_export_api(page)
    mock_tenants_api(page, tenants)
    mock_process_groups_api(page, process_groups)
    mock_create_process_model_api(page)


# ===================================================================
# Utilities
# ===================================================================


def make_template(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a copy of MOCK_TEMPLATE_PRIVATE with optional overrides."""
    tpl = copy.deepcopy(MOCK_TEMPLATE_PRIVATE)
    if overrides:
        tpl.update(overrides)
    return tpl


def make_tenant(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a copy of MOCK_TENANT_M8FLOW with optional overrides."""
    tpl = copy.deepcopy(MOCK_TENANT_M8FLOW)
    if overrides:
        tpl.update(overrides)
    return tpl


def generate_templates(count: int = 15) -> list[dict[str, Any]]:
    """Generate *count* unique mock templates for pagination tests."""
    return [
        make_template({
            "id": 1000 + i,
            "templateKey": f"gen-template-{i}",
            "name": f"Generated Template {i}",
            "description": f"Auto-generated template #{i}",
            "category": "Generated",
        })
        for i in range(count)
    ]


# ===================================================================
# Super Admin cross-tenant fixtures (read-only access model)
# ===================================================================
#
# The Super Admin role has cross-tenant *visibility* but is *read-only* on
# tenant data (process models/groups, process instances, secrets, connectors,
# templates -- export only). It retains full management of tenants, tenant
# users and tenant groups. The mocks below model exactly that so role-gating
# tests are deterministic regardless of the live QA token.


def mock_super_admin_permissions_api(page: Page) -> None:
    """Grant ``GET`` everywhere; allow writes only on tenant-management URIs.

    Models the new Super Admin permission set: cross-tenant read-only, except
    POST/PUT/DELETE on the tenant / tenant-realm / tenant-management endpoints
    (every such URI contains ``tenant``). Use this in restriction tests so the
    assertions hold even if the QA super-admin token drifts.
    """

    def _allowed(url: str, method: str) -> bool:
        if method.upper() == "GET":
            return True
        return "tenant" in url.lower()

    def _handle(route: Route) -> None:
        body = route.request.post_data
        if not body:
            _json_response(route, {"results": {}})
            return
        data = json.loads(body)
        reqs = data.get("requests_to_check", {})
        results: dict[str, Any] = {}
        for url, methods in reqs.items():
            if isinstance(methods, (list, dict)):
                results[url] = {m: _allowed(url, m) for m in methods}
            else:
                results[url] = methods
        _json_response(route, {"results": results})

    page.route("**/permissions-check*", _handle)


# ---- Secrets (Configuration) ----------------------------------------------
# Deliberately NO ``value`` field: the list endpoint never returns secret
# values, which is what keeps secret values masked in the UI.

MOCK_SECRET_M8FLOW: dict[str, Any] = {
    "id": 1,
    "key": "M8FLOW_API_KEY",
    "username": "admin",
    "tenantId": M8FLOW_TENANT_ID,
    "tenantName": "M8Flow",
}

MOCK_SECRET_ACME: dict[str, Any] = {
    "id": 2,
    "key": "ACME_DB_PASSWORD",
    "username": "acme-admin",
    "tenantId": ACME_TENANT_ID,
    "tenantName": "Acme Corp",
}

ALL_MOCK_SECRETS: list[dict[str, Any]] = [MOCK_SECRET_M8FLOW, MOCK_SECRET_ACME]

_SECRET_DETAIL_RE = re.compile(r"/secrets/[^/?]+")


def mock_secrets_api(
    page: Page,
    secrets: list[dict[str, Any]] | None = None,
) -> None:
    """Intercept GET ``/secrets`` (list) and honor the ``tenantId`` filter.

    Returns records with tenant info but no plaintext value (masking). Detail
    requests (``/secrets/<key>``) fall through to the real backend.
    """
    source = secrets if secrets is not None else ALL_MOCK_SECRETS

    def _handle(route: Route) -> None:
        url = route.request.url
        if route.request.method != "GET" or _SECRET_DETAIL_RE.search(urlparse(url).path):
            route.fallback()
            return
        qs = parse_qs(urlparse(url).query)
        items = list(source)
        if "tenantId" in qs:
            tid = qs["tenantId"][0]
            items = [s for s in items if s.get("tenantId") == tid]
        page_slice, pagination = _paginate_template_results(items, url)
        _json_response(route, {"results": page_slice, "pagination": pagination})

    page.route("**/secrets*", _handle)


# ---- Connectors ------------------------------------------------------------
# Connectors are global plugin definitions (not tenant-scoped); the grouped
# endpoint returns the same catalogue regardless of the selected tenant.

MOCK_CONNECTOR_HTTP: dict[str, Any] = {
    "id": "http",
    "name": "HTTP",
    "description": "Make HTTP requests to external services.",
    "status": "available",
    "icon": "",
    "operationCount": 2,
    "operations": [
        {
            "id": "http/GetRequest",
            "name": "Get Request",
            "rawName": "GetRequest",
            "description": "Perform an HTTP GET request.",
            "parameters": [{"id": "url", "type": "str", "required": True}],
        },
        {
            "id": "http/PostRequest",
            "name": "Post Request",
            "rawName": "PostRequest",
            "description": "Perform an HTTP POST request.",
            "parameters": [{"id": "url", "type": "str", "required": True}],
        },
    ],
}

MOCK_CONNECTOR_SLACK: dict[str, Any] = {
    "id": "slack",
    "name": "Slack",
    "description": "Send messages to Slack channels.",
    "status": "available",
    "icon": "",
    "operationCount": 1,
    "operations": [
        {
            "id": "slack/PostMessage",
            "name": "Post Message",
            "rawName": "PostMessage",
            "description": "Post a message to a channel.",
            "parameters": [{"id": "channel", "type": "str", "required": True}],
        },
    ],
}

ALL_MOCK_CONNECTORS: list[dict[str, Any]] = [MOCK_CONNECTOR_HTTP, MOCK_CONNECTOR_SLACK]


def mock_connectors_api(
    page: Page,
    connectors: list[dict[str, Any]] | None = None,
) -> None:
    """Intercept GET ``/m8flow/connectors-grouped`` and return the catalogue."""
    source = connectors if connectors is not None else ALL_MOCK_CONNECTORS

    def _handle(route: Route) -> None:
        if route.request.method != "GET":
            route.fallback()
            return
        _json_response(route, source)

    page.route("**/m8flow/connectors-grouped*", _handle)


# ---- Process instances -----------------------------------------------------

MOCK_PROCESS_INSTANCE_M8FLOW: dict[str, Any] = {
    "id": 5001,
    "process_model_identifier": "test-group/m8flow-model",
    "process_model_display_name": "M8Flow Onboarding",
    "status": "complete",
    "start_in_seconds": 1700000000,
    "end_in_seconds": 1700000500,
    "tenantId": "m8flow",
    "tenantName": "M8Flow",
}

MOCK_PROCESS_INSTANCE_ACME: dict[str, Any] = {
    "id": 5002,
    "process_model_identifier": "test-group/acme-model",
    "process_model_display_name": "Acme Invoice",
    "status": "error",
    "start_in_seconds": 1700100000,
    "end_in_seconds": None,
    "tenantId": "acme",
    "tenantName": "Acme Corp",
}

MOCK_PROCESS_INSTANCE_SUSPENDED: dict[str, Any] = {
    "id": 5003,
    "process_model_identifier": "test-group/acme-model",
    "process_model_display_name": "Acme Refund",
    "status": "suspended",
    "start_in_seconds": 1700200000,
    "end_in_seconds": None,
    "tenantId": "acme",
    "tenantName": "Acme Corp",
}

ALL_MOCK_PROCESS_INSTANCES: list[dict[str, Any]] = [
    MOCK_PROCESS_INSTANCE_M8FLOW,
    MOCK_PROCESS_INSTANCE_ACME,
    MOCK_PROCESS_INSTANCE_SUSPENDED,
]

_PROCESS_INSTANCE_COLUMNS: list[dict[str, Any]] = [
    {"Header": "Id", "accessor": "id", "filterable": False},
    {"Header": "Process", "accessor": "process_model_display_name", "filterable": False},
    {"Header": "Start", "accessor": "start_in_seconds", "filterable": False},
    {"Header": "Status", "accessor": "status", "filterable": False},
]

_PROCESS_INSTANCE_LIST_RE = re.compile(r"/process-instances(/for-me)?(\?|$)")


def mock_process_instances_api(
    page: Page,
    instances: list[dict[str, Any]] | None = None,
) -> None:
    """Intercept the process-instance list/report endpoint.

    Returns a paginated report payload. The frontend injects a ``tenantName``
    column client-side for super admins, so the mock only supplies the data and
    the base columns. Honors the ``x-m8flow-tenant-id`` request header for
    cross-tenant isolation assertions.
    """
    source = instances if instances is not None else ALL_MOCK_PROCESS_INSTANCES

    def _handle(route: Route) -> None:
        url = route.request.url
        path = urlparse(url).path
        if not _PROCESS_INSTANCE_LIST_RE.search(path):
            route.fallback()
            return
        items = list(source)
        tid = route.request.headers.get("x-m8flow-tenant-id")
        if tid:
            items = [i for i in items if i.get("tenantId") == tid]
        page_slice, pagination = _paginate_template_results(items, url)
        _json_response(route, {
            "results": page_slice,
            "pagination": pagination,
            "report_metadata": {
                "columns": copy.deepcopy(_PROCESS_INSTANCE_COLUMNS),
                "filter_by": [],
                "order_by": [],
            },
            "report_hash": "mock-process-instance-hash",
        })

    page.route(re.compile(r".*/process-instances(/for-me)?(\?.*)?$"), _handle)


# ---- Cross-tenant process groups / models ---------------------------------

MOCK_PROCESS_GROUP_M8FLOW: dict[str, Any] = {
    "id": "m8flow-group",
    "display_name": "M8Flow Operations",
    "description": "Process group owned by M8Flow",
    "tenantId": M8FLOW_TENANT_ID,
    "tenantName": "M8Flow",
    # A model inside the group so drill-in tests can exercise the model card.
    "process_models": [
        {
            "id": "m8flow-group/onboarding",
            "display_name": "M8Flow Onboarding",
            "description": "Onboarding workflow",
            "tenantId": M8FLOW_TENANT_ID,
            "tenantName": "M8Flow",
        }
    ],
    "process_groups": [],
}

MOCK_PROCESS_GROUP_ACME: dict[str, Any] = {
    "id": "acme-group",
    "display_name": "Acme Finance",
    "description": "Process group owned by Acme Corp",
    "tenantId": ACME_TENANT_ID,
    "tenantName": "Acme Corp",
    "process_models": [],
    "process_groups": [],
}

ALL_MOCK_CROSS_TENANT_GROUPS: list[dict[str, Any]] = [
    MOCK_PROCESS_GROUP_M8FLOW,
    MOCK_PROCESS_GROUP_ACME,
]


# ---- Home (tasks) ----------------------------------------------------------

MOCK_TASK_M8FLOW: dict[str, Any] = {
    "id": 9001,
    "process_instance_id": 9001,
    "task_id": "Task_m8flow_1",
    "process_model_identifier": "m8flow-group/onboarding",
    "process_model_display_name": "M8Flow Onboarding Task",
    "task_title": "Approve M8Flow Onboarding",
    "task_name": "approve_m8flow",
    "process_initiator_username": "admin",
    "potential_owner_usernames": "admin",
    "last_milestone_bpmn_name": "Started",
    "created_at_in_seconds": 1700000000,
    "updated_at_in_seconds": 1700000100,
    "tenantId": M8FLOW_TENANT_ID,
    "tenantName": "M8Flow",
}

MOCK_TASK_ACME: dict[str, Any] = {
    "id": 9002,
    "process_instance_id": 9002,
    "task_id": "Task_acme_1",
    "process_model_identifier": "acme-group/invoice",
    "process_model_display_name": "Acme Invoice Task",
    "task_title": "Review Acme Invoice",
    "task_name": "review_acme",
    "process_initiator_username": "acme-admin",
    "potential_owner_usernames": "acme-admin",
    "last_milestone_bpmn_name": "Started",
    "created_at_in_seconds": 1700100000,
    "updated_at_in_seconds": 1700100100,
    "tenantId": ACME_TENANT_ID,
    "tenantName": "Acme Corp",
}

ALL_MOCK_TASKS: list[dict[str, Any]] = [MOCK_TASK_M8FLOW, MOCK_TASK_ACME]


# ---- Templates (cross-tenant) ---------------------------------------------

# Whole catalogue across tenants, for "view templates from all tenants" tests.
CROSS_TENANT_GALLERY_TEMPLATES: list[dict[str, Any]] = [
    *ALL_MOCK_TEMPLATES,
    *ALL_ACME_TEMPLATES,
]

# Id-keyed pair for per-tenant filter tests (separate from the shared
# ALL_MOCK_TEMPLATES, which other suites depend on, so we never mutate those).
CROSS_TENANT_SCOPED_TEMPLATES: list[dict[str, Any]] = [
    make_template({"id": 7001, "templateKey": "m8flow-tpl", "name": "M8Flow Scoped Template", "tenantId": M8FLOW_TENANT_ID}),
    make_template({"id": 7002, "templateKey": "acme-tpl", "name": "Acme Scoped Template", "tenantId": ACME_TENANT_ID}),
]


def mock_tasks_api(
    page: Page,
    tasks: list[dict[str, Any]] | None = None,
) -> None:
    """Intercept GET ``/tasks`` (home page) and honor the ``tenantId`` filter.

    The home page sends ``?tenantId=`` when a super admin selects a tenant in
    the global tenant filter.
    """
    source = tasks if tasks is not None else ALL_MOCK_TASKS

    def _handle(route: Route) -> None:
        url = route.request.url
        if route.request.method != "GET":
            route.fallback()
            return
        items = list(source)
        qs = parse_qs(urlparse(url).query)
        if "tenantId" in qs:
            tid = qs["tenantId"][0]
            items = [task for task in items if task.get("tenantId") == tid]
        _json_response(route, {"results": items, "pagination": _make_pagination(items)})

    page.route("**/tasks*", _handle)
