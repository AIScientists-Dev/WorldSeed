"""Background tick loop — runs engine ticks and triggers notifications."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from worldseed.connector.base import ConnectorProvider
    from worldseed.world import WorldEngine

log = structlog.get_logger()


async def evaluate_and_notify(
    engine: WorldEngine,
    connector: ConnectorProvider | None,
    ticks_since_notify: dict[str, int],
    agents_ready: set[str] | None = None,
    busy_tracker: BusyTracker | None = None,
) -> set[str]:
    """Evaluate wakeup conditions and send notifications.

    Standalone function — called by tick_runner._loop and tick/step endpoint.
    No busy gating — OpenClaw collect mode handles message queuing.

    Returns set of agent_ids that failed to notify.
    """
    if connector is None:
        return set()

    wakeups = engine.get_wakeup_results()
    urgent_map = {w.agent_id: w for w in wakeups if w.should_wake}

    # Phase 1: collect who to wake + their perception data
    # Each tuple: (agent_id, reason, perception_dict)
    to_notify: list[tuple[str, str, dict[str, Any]]] = []

    for agent_id in engine.get_registered_agents():
        interval = engine.get_think_interval(agent_id)
        # Default to interval-1 so first tick triggers immediately
        ticks_since_notify.setdefault(agent_id, interval - 1)
        ticks_since_notify[agent_id] += 1

        urgent = urgent_map.get(agent_id)
        reason: str | None = None
        if urgent and (engine.get_wake_on_push(agent_id) or urgent.reason == "whisper"):
            reason = f"urgent: {urgent.reason}"
        elif ticks_since_notify[agent_id] >= interval:
            reason = "regular"

        if reason is not None:
            # Full perception every wake — no delta.
            # Gateway plugin uses wake_summary to select what to display.
            perception = engine.peek_perception(agent_id)
            to_notify.append((agent_id, reason, perception))
            ticks_since_notify[agent_id] = 0

            # Record actual inbox payload (events + DMs), not full perception
            inbox_data = engine.peek_inbox(agent_id)
            engine.recorder.record(
                "wakeup",
                engine.tick,
                agent_id=agent_id,
                reason=reason,
                events=[e.to_dict() for e in inbox_data["events"]],
                whispers=[m.to_dict() for m in inbox_data["whispers"]],
            )

    # Phase 2: send all wakes in parallel, drain only on success
    failed: set[str] = set()
    if to_notify:
        results = await asyncio.gather(
            *[connector.notify(aid, reason, perc) for aid, reason, perc in to_notify],
            return_exceptions=True,
        )
        for (aid, _, _), result in zip(to_notify, results):
            if isinstance(result, Exception):
                log.warning("wake_send_failed", agent=aid, error=str(result))
                failed.add(aid)
            else:
                engine.drain_inbox(aid)
    return failed


class BusyTracker:
    """Tracks which agents have been woken but haven't responded yet.

    Prevents wake message accumulation when agents are slow to respond.
    """

    def __init__(self, timeout: float = 120.0) -> None:
        if timeout <= 0:
            log.warning("wake_timeout_clamped", requested=timeout)
            timeout = 40.0
        self._timeout = timeout
        self._busy_since: dict[str, float] = {}
        self._pending_wake: dict[str, bool] = {}

    def is_busy(self, agent_id: str) -> bool:
        return agent_id in self._busy_since

    def mark_busy(self, agent_id: str) -> None:
        self._busy_since[agent_id] = time.monotonic()
        self._pending_wake.pop(agent_id, None)

    def clear_busy(self, agent_id: str) -> bool:
        """Clear busy state. Returns True if there was a pending wake."""
        self._busy_since.pop(agent_id, None)
        return self._pending_wake.pop(agent_id, False)

    def set_pending(self, agent_id: str) -> None:
        """Mark that an urgent wake arrived while agent was busy."""
        self._pending_wake[agent_id] = True

    def clear_all(self) -> None:
        """Clear all busy states (gateway disconnected)."""
        if self._busy_since:
            log.info("busy_cleared_gateway_disconnect", agents=list(self._busy_since))
        self._busy_since.clear()
        self._pending_wake.clear()

    def check_timeouts(self) -> list[str]:
        """Return and clear agents that have timed out."""
        now = time.monotonic()
        timed_out = []
        for agent_id in list(self._busy_since):
            if now - self._busy_since[agent_id] >= self._timeout:
                log.warning(
                    "busy_timeout",
                    agent=agent_id,
                    elapsed_s=round(now - self._busy_since[agent_id], 1),
                )
                self._busy_since.pop(agent_id)
                self._pending_wake.pop(agent_id, None)
                timed_out.append(agent_id)
        return timed_out


class TickRunner:
    """Runs engine ticks in a background asyncio task."""

    def __init__(
        self,
        engine: WorldEngine,
        connector: ConnectorProvider | None = None,
        interval: float = 1.0,
        wake_timeout: float = 40.0,
    ) -> None:
        self._engine = engine
        self._connector = connector
        self._interval = interval
        self._max_ticks = engine.config.scene.max_ticks
        self._timeout_sec: float | None = (
            engine.config.scene.timeout_min * 60 if engine.config.scene.timeout_min is not None else None
        )
        self._start_time: float = 0.0
        self._task: asyncio.Task[None] | None = None
        self._ticks_since_notify: dict[str, int] = {}
        self.busy = BusyTracker(timeout=wake_timeout)
        self._notifying = False
        self._pending_notify = False

    @property
    def connector(self) -> ConnectorProvider | None:
        """Current connector (may be set after init for deferred wiring)."""
        return self._connector

    @connector.setter
    def connector(self, value: ConnectorProvider | None) -> None:
        self._connector = value

    @property
    def running(self) -> bool:
        """Whether the tick loop is running."""
        return self._task is not None and not self._task.done()

    def set_interval(self, interval: float) -> None:
        """Change tick interval at runtime."""
        self._interval = interval

    async def start(self) -> None:
        """Start the background tick loop."""
        if self.running:
            return
        self._start_time = time.monotonic()
        self._task = asyncio.create_task(self._loop())
        log.info("tick_runner_started", interval=self._interval)
        if self._max_ticks is not None:
            log.warning(
                "max_ticks_limit",
                max_ticks=self._max_ticks,
                hint="set scene.max_ticks in config to override (null for unlimited)",
            )
        else:
            log.info("max_ticks_unlimited")

    async def stop(self) -> None:
        """Stop the background tick loop."""
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        log.info("tick_runner_stopped")

    async def _loop(self) -> None:
        """Main tick loop with drift protection."""
        loop = asyncio.get_running_loop()
        next_tick = loop.time() + self._interval
        while True:
            try:
                results = await self._engine.step_async()
                if results:
                    log.debug(
                        "tick_complete",
                        tick=self._engine.tick,
                        actions=len(results),
                    )

                # Check every tick regardless of activity
                await self._guarded_notify()

                # Auto-stop on game_over event
                if self._engine.event_log.get_events(event_type="game_over"):
                    log.info(
                        "game_over_detected",
                        tick=self._engine.tick,
                    )
                    break

                # Auto-stop after max_ticks
                if self._max_ticks is not None and self._engine.tick >= self._max_ticks:
                    log.info(
                        "max_ticks_reached",
                        tick=self._engine.tick,
                        max_ticks=self._max_ticks,
                    )
                    break

                # Auto-stop after timeout_min
                if self._timeout_sec is not None and time.monotonic() - self._start_time >= self._timeout_sec:
                    log.info(
                        "timeout_reached",
                        tick=self._engine.tick,
                        elapsed_min=round((time.monotonic() - self._start_time) / 60, 2),
                    )
                    break

            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("tick_error", tick=self._engine.tick)

            now = loop.time()
            delay = next_tick - now
            if delay > 0:
                await asyncio.sleep(delay)
            else:
                log.warning("tick_overrun", behind_s=round(-delay, 3))
            next_tick += self._interval

    async def _guarded_notify(self) -> set[str]:
        """Run evaluate_and_notify with concurrency guard. Returns failed agent IDs."""
        self._notifying = True
        try:
            failed = await evaluate_and_notify(
                self._engine,
                self._connector,
                self._ticks_since_notify,
                busy_tracker=self.busy,
            )
        finally:
            self._notifying = False

        # Process any requests that arrived during notify
        while self._pending_notify:
            self._pending_notify = False
            self._notifying = True
            try:
                more_failed = await evaluate_and_notify(
                    self._engine,
                    self._connector,
                    self._ticks_since_notify,
                    busy_tracker=self.busy,
                )
                failed |= more_failed
            finally:
                self._notifying = False
        return failed

    async def request_immediate_notify(self) -> set[str]:
        """Request immediate evaluate_and_notify. Returns failed agent IDs.

        If the loop is running and currently notifying, sets pending flag.
        If the loop is running but not notifying, runs directly.
        If the loop is stopped (paused), runs directly — no concurrency risk.
        """
        if self._notifying:
            self._pending_notify = True
            return set()
        return await self._guarded_notify()
