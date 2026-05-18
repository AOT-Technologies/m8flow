"""Start-form helpers for dynamic complaint type (Hardware / Software)."""

from __future__ import annotations

import re
from typing import Literal

from playwright.sync_api import Page, expect

from helpers.config import PAGE_DATA_TIMEOUT
from helpers.waiters import wait_for_app_ready

ComplaintType = Literal["Hardware", "Software"]


def select_complaint_type_and_submit_start_form(page: Page, choice: ComplaintType) -> None:
    """Pick complaint type from 'Complaint Type' combobox and submit."""
    complaint_dropdown = page.get_by_role(
        "combobox",
        name="Complaint Type",
    ).first
    expect(complaint_dropdown).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    complaint_dropdown.click()

    option = page.get_by_role(
        "option",
        name=re.compile(rf"^\s*{re.escape(choice)}\s*$", re.I),
    ).first
    expect(option).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    option.click()

    submit = page.get_by_role(
        "button",
        name=re.compile(r"submit|continue|next|^save\b", re.I),
    ).first
    expect(submit).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    submit.click()
    wait_for_app_ready(page)
