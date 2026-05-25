from playwright.sync_api import Page


def print_page_details(page: Page) -> None:
    """Print data-testid elements and interactable controls for debugging."""
    page.wait_for_load_state()

    print("\n--- Elements with data-testid ---")
    elements_with_testid = page.query_selector_all("[data-testid]")
    if not elements_with_testid:
        print("No elements with data-testid found.")
    else:
        for element in elements_with_testid:
            data_testid = element.get_attribute("data-testid")
            tag_name = element.evaluate("el => el.tagName.toLowerCase()")
            if data_testid and tag_name != "svg":
                print(f"  <{tag_name}> data-testid={data_testid}")

    print("\n--- Input and Button Elements ---")
    interactable = page.query_selector_all(
        'input, button, a[role="button"], select, textarea'
    )
    if not interactable:
        print("No interactable elements found.")
    else:
        for element in interactable:
            if element.get_attribute("data-testid"):
                continue
            tag_name = element.evaluate("el => el.tagName.toLowerCase()")
            el_id = element.get_attribute("id")
            el_name = element.get_attribute("name")
            aria_label = element.get_attribute("aria-label")
            parts = [f"<{tag_name}>"]
            if el_id:
                parts.append(f"id='{el_id}'")
            if el_name:
                parts.append(f"name='{el_name}'")
            if aria_label:
                parts.append(f"aria-label='{aria_label}'")
            print(f"  {', '.join(parts)}")
