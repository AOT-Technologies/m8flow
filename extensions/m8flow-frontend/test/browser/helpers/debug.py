"""Playwright page dump helpers for local browser-test debugging."""

from __future__ import annotations

from playwright.sync_api import Page

_TESTID_SELECTOR = "[data-testid]"
_CONTROL_SELECTOR = 'input, button, a[role="button"], select, textarea'


def dump_page_for_debug(page: Page) -> None:
    """Write a short inventory of testids and unlabeled controls to stdout."""
    page.wait_for_load_state()
    _emit_testid_inventory(page)
    _emit_control_inventory(page)


# Back-compat alias used by ad-hoc debugging sessions.
print_page_details = dump_page_for_debug


def _emit_testid_inventory(page: Page) -> None:
    print("\n--- Elements with data-testid ---")
    nodes = page.query_selector_all(_TESTID_SELECTOR)
    if not nodes:
        print("No elements with data-testid found.")
        return
    for node in nodes:
        testid = node.get_attribute("data-testid")
        tag = node.evaluate("n => n.tagName.toLowerCase()")
        if testid and tag != "svg":
            print(f"  <{tag}> data-testid={testid}")


def _emit_control_inventory(page: Page) -> None:
    print("\n--- Input and Button Elements ---")
    nodes = page.query_selector_all(_CONTROL_SELECTOR)
    if not nodes:
        print("No interactable elements found.")
        return
    for node in nodes:
        if node.get_attribute("data-testid"):
            continue
        tag = node.evaluate("n => n.tagName.toLowerCase()")
        attrs = []
        for key in ("id", "name", "aria-label"):
            value = node.get_attribute(key)
            if value:
                attrs.append(f"{key}='{value}'")
        suffix = f", {', '.join(attrs)}" if attrs else ""
        print(f"  <{tag}>{suffix}")
