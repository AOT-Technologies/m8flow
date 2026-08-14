"""Process Instances — tenant-admin list does not inject a tenant_id filter (CHK-10)."""
from __future__ import annotations

import logging

from playwright.sync_api import expect

from helpers.config import ELEMENT_TIMEOUT, PAGE_DATA_TIMEOUT
from helpers.mocks import (
    is_process_instance_list_post,
    make_process_instances,
    mock_process_instances_api,
    tenant_id_filters_from_post,
)
from process_instances._process_instances_page import ProcessInstancesPage

logger = logging.getLogger(__name__)


def test_tenant_admin_keeps_for_me_and_omits_tenant_id_filter(
    process_instances_page: ProcessInstancesPage,
) -> None:
    """CHK-10: tenant-admin keeps For Me and does not send a tenant_id report filter."""
    pip = process_instances_page
    mock_process_instances_api(pip.page, make_process_instances(2))

    with pip.page.expect_request(
        is_process_instance_list_post, timeout=PAGE_DATA_TIMEOUT
    ) as pending:
        pip.open("all")

    expect(pip.for_me_tab).to_be_visible(timeout=ELEMENT_TIMEOUT)
    filters = tenant_id_filters_from_post(pending.value)
    assert filters == [], (
        f"Tenant-admin process-instances POST must not include tenant_id, got {filters!r}"
    )
    logger.info("Tenant-admin list kept For Me and omitted tenant_id from the POST.")
