"""Shared mock helpers for process-model context tests."""

from __future__ import annotations

import json
import re

from playwright.sync_api import Page, Route

from helpers.mocks import mock_process_groups_api
from helpers.process_group_setup import TEST_PROCESS_GROUP_DISPLAY_NAME

DEFAULT_BPMN_FILE = "random_file.bpmn"
MOCK_GROUP_ID = "test-group"
MOCK_MODEL_ID = "mock-breadcrumb-model"
MOCK_ENCODED_MODEL_ID = f"{MOCK_GROUP_ID}:{MOCK_MODEL_ID}"
MOCK_MODEL_DISPLAY_NAME = "Mock Breadcrumb Model"


def mock_existing_process_model_data(page: Page) -> None:
    """Mock one existing process model and its BPMN file endpoints."""
    groups = [
        {
            "id": MOCK_GROUP_ID,
            "display_name": TEST_PROCESS_GROUP_DISPLAY_NAME,
            "description": "A test process group for E2E tests",
            "process_models": [
                {
                    "id": f"{MOCK_GROUP_ID}/{MOCK_MODEL_ID}",
                    "display_name": MOCK_MODEL_DISPLAY_NAME,
                    "description": "Mock model for breadcrumb checks",
                    "primary_file_name": DEFAULT_BPMN_FILE,
                    "primary_process_id": "",
                },
            ],
            "process_groups": [],
        },
    ]
    mock_process_groups_api(page, groups=groups)

    def _handle_process_models(route: Route) -> None:
        url = route.request.url
        method = route.request.method
        if route.request.resource_type == "document" or method != "GET":
            route.fallback()
            return

        if re.search(r"/process-models/[^/]+/validate(?:\?|$)", url):
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"valid": True}),
            )
            return

        if re.search(r"/process-models/[^/]+/files/[^/?#]+(?:\?|$)", url):
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "name": DEFAULT_BPMN_FILE,
                        "type": "bpmn",
                        "file_contents": '<?xml version="1.0"?><bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"><bpmn:process id="p"><bpmn:startEvent id="StartEvent_1"/></bpmn:process></bpmn:definitions>',
                        "file_contents_hash": "mock-hash",
                        "references": [],
                    },
                ),
            )
            return

        if re.search(r"/process-models/[^/?#]+(?:\?|$)", url):
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "id": f"{MOCK_GROUP_ID}/{MOCK_MODEL_ID}",
                        "display_name": MOCK_MODEL_DISPLAY_NAME,
                        "description": "Mock model for breadcrumb checks",
                        "primary_file_name": DEFAULT_BPMN_FILE,
                        "is_executable": True,
                        "files": [
                            {
                                "name": DEFAULT_BPMN_FILE,
                                "file_contents_hash": "mock-hash",
                                "type": "bpmn",
                            },
                        ],
                    },
                ),
            )
            return

        route.fallback()

    page.route(re.compile(r".*/process-models.*"), _handle_process_models)


def mock_process_group_detail_for_edit(page: Page) -> None:
    """Serve a process-group detail payload expected by the edit page."""

    def _handle_detail(route: Route) -> None:
        if route.request.resource_type == "document":
            route.fallback()
            return
        if route.request.method != "GET":
            route.fallback()
            return
        if not re.search(r"/process-groups/[^/?#]+$", route.request.url):
            route.fallback()
            return
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "id": "test-group",
                    "display_name": TEST_PROCESS_GROUP_DISPLAY_NAME,
                    "description": "A test process group for E2E tests",
                    "process_models": [],
                    "process_groups": [],
                },
            ),
        )

    page.route(re.compile(r".*/process-groups/[^/?#]+$"), _handle_detail)
