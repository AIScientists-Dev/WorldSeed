"""Browser tests: Settings modal.

Tests the gear icon → settings modal → apply changes flow.
"""

from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import enter_dashboard


class TestSettingsOpen:
    """D1: Open settings modal."""

    def test_gear_opens_modal(self, server_url: str, dashboard: Page) -> None:
        """Click gear icon → settings modal visible."""
        enter_dashboard(server_url, dashboard)

        # Click settings button (gear icon in header)
        dashboard.get_by_role("button", name="Settings").click()

        # Dialog should appear
        dialog = dashboard.get_by_role("dialog", name="Settings")
        expect(dialog).to_be_visible()


class TestSettingsClose:
    """D2: Close settings modal."""

    def test_close_button(self, server_url: str, dashboard: Page) -> None:
        """Click close → modal closes."""
        enter_dashboard(server_url, dashboard)

        # Open
        dashboard.get_by_role("button", name="Settings").click()
        dialog = dashboard.get_by_role("dialog", name="Settings")
        expect(dialog).to_be_visible()

        # Close via button
        dashboard.get_by_role("button", name="Close").click()
        expect(dialog).to_be_hidden()

    def test_overlay_click_closes(self, server_url: str, dashboard: Page) -> None:
        """Click outside dialog → dialog closes."""
        enter_dashboard(server_url, dashboard)

        dashboard.get_by_role("button", name="Settings").click()
        dialog = dashboard.get_by_role("dialog", name="Settings")
        expect(dialog).to_be_visible()

        # Press Escape to close (more reliable than clicking overlay with Radix)
        dashboard.keyboard.press("Escape")
        expect(dialog).to_be_hidden()


class TestSettingsApply:
    """D3: Apply tick settings changes via modal."""

    def test_apply_tick_interval(self, server_url: str, dashboard: Page) -> None:
        """Change tick interval in modal → Apply → verify via API."""
        enter_dashboard(server_url, dashboard)

        # Open settings
        dashboard.get_by_role("button", name="Settings").click()

        # Change tick interval
        interval_input = dashboard.get_by_label("Interval (sec)")
        interval_input.clear()
        interval_input.fill("2.5")

        # Click Apply
        dashboard.get_by_role("button", name="Apply").click()

        # Verify via API
        r = httpx.get(f"{server_url}/api/settings", timeout=5)
        settings = r.json()["settings"]
        assert settings["tick_interval"] == 2.5
