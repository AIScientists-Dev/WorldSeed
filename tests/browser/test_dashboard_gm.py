"""Browser tests: Dashboard — GM/Map View.

Tests the main dashboard view (map + right panel with GM data).
World must be started first, so tests use the API to start before navigating.
"""

from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import enter_dashboard, stop_world


def _switch_to_inspector(page: Page) -> None:
    """Switch the right panel from stream to data inspector."""
    btn = page.get_by_role("button", name="Data inspector")
    btn.click()
    page.wait_for_selector(".ent-group-hdr", timeout=10000)


class TestDashboardTransition:
    """B1: Lobby → Dashboard transition renders correctly."""

    def test_header_visible(self, server_url: str, dashboard: Page) -> None:
        """After start, header is visible with brand."""
        enter_dashboard(server_url, dashboard)
        expect(dashboard.locator("header")).to_be_visible()
        expect(dashboard.locator("header")).to_contain_text("WORLDSEED")

    def test_right_panel_visible(self, server_url: str, dashboard: Page) -> None:
        """Right panel area is visible."""
        enter_dashboard(server_url, dashboard)
        panel = dashboard.locator(".content-right")
        expect(panel).to_be_visible(timeout=10000)


class TestDashboardEntities:
    """B3: Entity list renders in data inspector panel."""

    def test_entities_render(self, server_url: str, dashboard: Page) -> None:
        """Entities from state API appear in the inspector panel."""
        enter_dashboard(server_url, dashboard)
        _switch_to_inspector(dashboard)
        group_hdrs = dashboard.locator(".ent-group-hdr")
        assert group_hdrs.count() > 0, "Should have entity type group headers"

    def test_entity_types_include_agent_and_space(self, server_url: str, dashboard: Page) -> None:
        """Bunker config has agent, space, resource entity types."""
        enter_dashboard(server_url, dashboard)
        _switch_to_inspector(dashboard)
        all_text = dashboard.locator(".ent-group-hdr").all_text_contents()
        type_names = [t.split("(")[0].strip().lower() for t in all_text]
        assert "agent" in type_names, f"Should have agent type, got: {type_names}"
        assert "space" in type_names, f"Should have space type, got: {type_names}"


class TestEntityExpandCollapse:
    """B4: Click entity to collapse/expand properties.

    Entities start expanded by default. First click collapses, second expands.
    """

    def test_collapse_entity(self, server_url: str, dashboard: Page) -> None:
        """Click expanded entity → properties become hidden."""
        enter_dashboard(server_url, dashboard)
        _switch_to_inspector(dashboard)
        first_entity = dashboard.locator(".ent-card").first
        detail = first_entity.locator(".ent-detail")
        # Starts expanded
        expect(detail).to_be_visible()
        first_entity.click()
        expect(detail).to_be_hidden()

    def test_reexpand_entity(self, server_url: str, dashboard: Page) -> None:
        """Click collapsed entity again → properties visible again."""
        enter_dashboard(server_url, dashboard)
        _switch_to_inspector(dashboard)
        first_entity = dashboard.locator(".ent-card").first
        detail = first_entity.locator(".ent-detail")
        # Collapse first
        first_entity.click()
        expect(detail).to_be_hidden()
        # Re-expand
        first_entity.click()
        expect(detail).to_be_visible()


class TestEntityInlineEdit:
    """B5: Click property value → edit inline → save."""

    def test_edit_property(self, server_url: str, dashboard: Page) -> None:
        """Click a property value → input appears → type new value → Enter → saved."""
        enter_dashboard(server_url, dashboard)
        _switch_to_inspector(dashboard)

        # Entities start expanded — wait for properties to be visible
        dashboard.wait_for_selector(".prop-editable", timeout=5000)

        # Click first editable property
        prop_value = dashboard.locator(".prop-editable").first
        prop_value.click()

        # Input should appear
        edit_input = dashboard.locator(".prop-edit-input")
        expect(edit_input).to_be_visible()

        # Type and submit
        edit_input.fill("999")
        edit_input.press("Enter")

        # Saved indicator appears
        saved = dashboard.locator(".prop-saved")
        expect(saved).to_be_visible(timeout=3000)


class TestTickStep:
    """B8: Tick step advances via API."""

    def test_step_advances_tick(self, server_url: str, dashboard: Page) -> None:
        """Step via API → tick counter increments."""
        enter_dashboard(server_url, dashboard)

        r = httpx.get(f"{server_url}/health", timeout=5)
        tick_before = r.json()["tick"]

        httpx.post(f"{server_url}/api/tick/step", json={}, timeout=5)

        r = httpx.get(f"{server_url}/health", timeout=5)
        tick_after = r.json()["tick"]
        assert tick_after == tick_before + 1


class TestPauseResume:
    """B9: Pause and Resume change world status."""

    def test_resume_then_pause(self, server_url: str, dashboard: Page) -> None:
        """Resume → live. Pause → paused. Verified via API."""
        enter_dashboard(server_url, dashboard)

        httpx.post(f"{server_url}/api/tick/resume", json={}, timeout=5)
        r = httpx.get(f"{server_url}/health", timeout=5)
        assert r.json()["status"] == "live"

        httpx.post(f"{server_url}/api/tick/pause", json={}, timeout=5)
        r = httpx.get(f"{server_url}/health", timeout=5)
        assert r.json()["status"] == "paused"


class TestStopWorld:
    """B12: Stop World returns to lobby."""

    def test_stop_returns_to_lobby(self, server_url: str, dashboard: Page) -> None:
        """Stop via API → navigate to lobby → lands in lobby."""
        enter_dashboard(server_url, dashboard)
        stop_world(server_url)

        dashboard.goto(f"{server_url}/lobby")
        dashboard.wait_for_selector(".setup-page", timeout=10000)
        expect(dashboard.locator(".setup-brand")).to_be_visible()
