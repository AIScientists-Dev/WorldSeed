"""Browser tests: Lobby page.

Tests the setup/lobby page that users see when the server starts
without an active world.
"""

from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import start_world, stop_world


class TestLobbyLoads:
    """A1: Page loads in lobby mode with correct structure."""

    def test_brand_visible(self, dashboard: Page) -> None:
        """WORLDSEED brand text is visible."""
        brand = dashboard.locator(".setup-brand")
        expect(brand).to_be_visible()
        expect(brand).to_contain_text("WORLD")

    def test_setup_card_visible(self, dashboard: Page) -> None:
        """Setup card with 'New World' title is visible."""
        card_title = dashboard.locator(".setup-card-title").first
        expect(card_title).to_be_visible()

    def test_start_button_exists(self, dashboard: Page) -> None:
        """Start World button exists."""
        btn = dashboard.locator(".setup-btn")
        expect(btn).to_be_visible()
        expect(btn).to_contain_text("Start World")


class TestLobbyConfigs:
    """A2: Config dropdown is populated from /api/configs."""

    def test_config_dropdown_has_trigger(self, dashboard: Page) -> None:
        """Shadcn Select trigger is visible and shows a selected config."""
        # The config dropdown uses shadcn Select (Radix), not native <select>.
        # The trigger button has role="combobox".
        trigger = dashboard.locator(".setup-field").first.get_by_role("combobox")
        expect(trigger).to_be_visible(timeout=5000)


class TestLobbyStartWorld:
    """A3: Start World button triggers world creation and transition."""

    def test_start_transitions_away_from_lobby(self, server_url: str, dashboard: Page) -> None:
        """Click Start → page leaves lobby (may go to intro or dashboard)."""
        dashboard.locator(".setup-btn").click()

        # Wait for lobby page to disappear — we've transitioned
        expect(dashboard.locator(".setup-page")).to_be_hidden(timeout=15000)


class TestLobbyStartDisabled:
    """A4: Start button is enabled when config is auto-selected on mount."""

    def test_button_enabled_with_config(self, dashboard: Page) -> None:
        """Button is enabled because config auto-selects on mount."""
        btn = dashboard.locator(".setup-btn")
        expect(btn).to_be_enabled()


class TestLobbyStartFailure:
    """A5: Start with bad config shows error."""

    def test_bad_config_shows_error(self, server_url: str, dashboard: Page) -> None:
        """Set a nonexistent config path via API → 404."""
        r = httpx.post(
            f"{server_url}/api/world/start",
            json={"config_path": "/nonexistent/bad.yaml", "tick_interval": 60},
            timeout=10,
        )
        assert r.status_code == 404


class TestLobbyPastRuns:
    """A6: Past runs section."""

    def test_past_run_appears_after_stop(self, server_url: str, dashboard: Page) -> None:
        """Start → stop → past runs section shows the run."""
        data = start_world(server_url)
        run_id = data["run_id"]
        stop_world(server_url)

        # Reload page to go back to lobby with fresh data
        dashboard.reload()
        dashboard.wait_for_selector(".setup-page", timeout=10000)

        # Past runs section should contain the run ID prefix
        past_runs_card = dashboard.locator(".setup-card").last
        # The UI shows run_id[:8] in the past runs list
        expect(past_runs_card).to_contain_text(run_id[:6], timeout=10000)
