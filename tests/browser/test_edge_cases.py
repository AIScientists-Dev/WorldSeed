"""Browser tests: Edge cases.

Tests resilience scenarios — refresh, stop during view, empty worlds.
"""

from __future__ import annotations

from playwright.sync_api import Page, expect

from .conftest import enter_dashboard, start_world, stop_world


class TestRefreshDuringDashboard:
    """E1: Refresh page while on dashboard."""

    def test_refresh_lands_on_dashboard(self, server_url: str, dashboard: Page) -> None:
        """Refresh → route guard redirects to dashboard if world is running."""
        enter_dashboard(server_url, dashboard)
        expect(dashboard.locator("header")).to_be_visible()

        dashboard.reload()
        dashboard.wait_for_selector("header", timeout=10000)

    def test_refresh_can_reenter_dashboard(self, server_url: str, dashboard: Page) -> None:
        """After refresh, dashboard still works."""
        enter_dashboard(server_url, dashboard)
        dashboard.reload()
        dashboard.wait_for_selector("header", timeout=10000)
        expect(dashboard.locator("header")).to_contain_text("WORLDSEED")


class TestStopWhileViewing:
    """E2: Stop world while dashboard is open."""

    def test_stop_via_api_then_reload(self, server_url: str, dashboard: Page) -> None:
        """Stop world via API while on dashboard → reload → lands in lobby."""
        enter_dashboard(server_url, dashboard)
        stop_world(server_url)

        dashboard.goto(f"{server_url}/lobby")
        dashboard.wait_for_selector(".setup-page", timeout=10000)
        brand = dashboard.locator(".setup-brand")
        expect(brand).to_be_visible()


class TestEmptyWorld:
    """E3: World with zero agents."""

    def test_minimal_config_no_crash(self, server_url: str, dashboard: Page) -> None:
        """Start minimal.yaml → dashboard loads without crash."""
        data = start_world(server_url, config_name="minimal.yaml", tick_interval=60.0)
        run_id = data["run_id"]

        dashboard.goto(f"{server_url}/run/{run_id}/map")
        dashboard.wait_for_selector("header", timeout=10000)

        expect(dashboard.locator("header")).to_be_visible()

    def test_no_js_errors(self, server_url: str, dashboard: Page) -> None:
        """No uncaught JS errors during full lobby → dashboard → lobby cycle."""
        errors: list[str] = []
        dashboard.on("pageerror", lambda exc: errors.append(str(exc)))

        data = start_world(server_url, tick_interval=60.0)
        run_id = data["run_id"]

        # Navigate to lobby
        dashboard.goto(f"{server_url}/lobby")
        dashboard.wait_for_selector(".setup-page", timeout=10000)

        # Navigate to dashboard
        dashboard.goto(f"{server_url}/run/{run_id}/map")
        dashboard.wait_for_selector("header", timeout=10000)
        dashboard.wait_for_timeout(2000)

        # Navigate back to lobby
        dashboard.goto(f"{server_url}/lobby")
        dashboard.wait_for_selector(".setup-page", timeout=10000)

        assert errors == [], f"JS errors during navigation: {errors}"
