"""Browser tests: Dashboard — Agent View.

Tests the agent detail view when an agent is selected via direct URL navigation.
"""

from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import enter_dashboard


class TestAgentView:
    """Agent view renders correctly with sections."""

    def test_agent_panel_renders(self, server_url: str, dashboard: Page) -> None:
        """Navigate to agent URL → panel header shows agent name."""
        data = enter_dashboard(server_url, dashboard, step_first=True)
        run_id = data["run_id"]

        dashboard.goto(f"{server_url}/run/{run_id}/agent/old_chen")
        panel_label = dashboard.locator(".panel-label")
        expect(panel_label.first).to_contain_text("old_chen", timeout=10000)

    def test_visible_section_exists(self, server_url: str, dashboard: Page) -> None:
        """Visible entities section is always shown."""
        data = enter_dashboard(server_url, dashboard, step_first=True)
        run_id = data["run_id"]

        dashboard.goto(f"{server_url}/run/{run_id}/agent/old_chen")
        dashboard.wait_for_selector(".section-hdr", timeout=10000)

        visible_hdr = dashboard.locator(".section-hdr", has_text="Visible")
        expect(visible_hdr).to_be_visible()

    def test_inbox_section_exists(self, server_url: str, dashboard: Page) -> None:
        """Inbox section header is always visible."""
        data = enter_dashboard(server_url, dashboard, step_first=True)
        run_id = data["run_id"]

        dashboard.goto(f"{server_url}/run/{run_id}/agent/old_chen")
        dashboard.wait_for_selector(".section-hdr", timeout=10000)

        inbox_hdr = dashboard.locator(".section-hdr", has_text="Inbox")
        expect(inbox_hdr).to_be_visible()

    def test_whisper_section_exists(self, server_url: str, dashboard: Page) -> None:
        """Whisper input section is always visible."""
        data = enter_dashboard(server_url, dashboard, step_first=True)
        run_id = data["run_id"]

        dashboard.goto(f"{server_url}/run/{run_id}/agent/old_chen")
        dashboard.wait_for_selector(".section-hdr", timeout=10000)

        whisper_hdr = dashboard.locator(".section-hdr", has_text="Whisper")
        expect(whisper_hdr).to_be_visible()

    def test_whisper_appears_in_inbox(self, server_url: str, dashboard: Page) -> None:
        """Send a whisper via API → appears in agent's inbox view after poll."""
        data = enter_dashboard(server_url, dashboard, step_first=True)
        run_id = data["run_id"]

        # Send whisper before navigating to agent view
        httpx.post(
            f"{server_url}/api/whisper",
            json={"agent_id": "old_chen", "message": "test_whisper_xyz"},
            timeout=5,
        )

        # Verify whisper is in the inbox via API first
        r = httpx.get(f"{server_url}/api/inbox?agent_id=old_chen", timeout=5)
        assert "test_whisper_xyz" in r.text

        # Navigate to agent view — selectAgent fires on mount, triggers
        # pollAgentData which fetches /api/inbox
        dashboard.goto(f"{server_url}/run/{run_id}/agent/old_chen")
        dashboard.wait_for_selector(".section-hdr", timeout=10000)

        # Wait for inbox item — poll interval is 10s, initial fetch is immediate
        inbox_item = dashboard.locator(".inbox-item", has_text="test_whisper_xyz")
        expect(inbox_item).to_be_visible(timeout=20000)

    def test_return_to_map_view(self, server_url: str, dashboard: Page) -> None:
        """Navigate from agent view back to map view."""
        data = enter_dashboard(server_url, dashboard, step_first=True)
        run_id = data["run_id"]

        dashboard.goto(f"{server_url}/run/{run_id}/agent/old_chen")
        dashboard.wait_for_selector(".panel-label", timeout=10000)

        dashboard.goto(f"{server_url}/run/{run_id}/map")
        dashboard.wait_for_selector("header", timeout=10000)
        expect(dashboard.locator("header")).to_contain_text("WORLDSEED")
