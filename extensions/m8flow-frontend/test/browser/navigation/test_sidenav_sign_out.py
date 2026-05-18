"""SideNav sign-out test."""

from playwright.sync_api import Page, expect

from helpers.login import expect_logged_out


def test_sidenav_sign_out(authenticated_page: Page) -> None:
    page = authenticated_page
    user_menu = page.get_by_test_id("nav-user-actions-button")
    expect(user_menu).to_be_visible()
    user_menu.click()
    page.get_by_test_id("sign-out-button").click()
    expect_logged_out(page)

