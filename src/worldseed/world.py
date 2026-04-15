"""WorldEngine — top-level facade for running a world.

Delegates to specialized components:
  StateStore      — entity CRUD
  EventLog        — event storage + TTL
  TickEngine      — tick orchestration
  AgentRegistry   — agent lifecycle + profiles + think_interval
  WakeupEvaluator — notify triggers
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import TYPE_CHECKING, Any

from worldseed.agent_registry import AgentRegistry
from worldseed.engine.action_queue import ActionQueue
from worldseed.engine.event_log import EventLog
from worldseed.engine.inbox import InboxManager, InboxWhisper
from worldseed.engine.rules_engine import ActionResult
from worldseed.engine.state_store import StateStore
from worldseed.engine.tick import TickEngine
from worldseed.engine.wakeup import WakeupEvaluator, WakeupResult
from worldseed.models.action import ActionSubmission
from worldseed.models.event import Event
from worldseed.persistence import NullRecorder
from worldseed.protocol.agent import AgentPerception, build_perception
from worldseed.scene.config import load_config
from worldseed.scene.populator import populate

if TYPE_CHECKING:
    from worldseed.dm.providers.base import DMProvider
    from worldseed.models.config_schema import AgentConfig, SceneConfig
    from worldseed.persistence import RunRecorder


class WorldEngine:
    """Facade: load config, register agents, submit actions, step ticks."""

    def __init__(
        self,
        config_path: str | Path | None = None,
        dm_provider: DMProvider | None = None,
        *,
        config: SceneConfig | None = None,
        recorder: RunRecorder | NullRecorder | None = None,
        language: str = "",
    ) -> None:
        if config is not None:
            self._config = config
        elif config_path is not None:
            self._config = load_config(config_path)
        else:
            msg = "Either config_path or config must be provided"
            raise ValueError(msg)

        self.recorder: RunRecorder | NullRecorder = recorder or NullRecorder()
        self.state = StateStore()
        self.event_log = EventLog()
        self._queue = ActionQueue()
        self._inbox_manager = InboxManager()
        self.registry = AgentRegistry(self._config, self.state)

        self._tick_engine = TickEngine(
            self._config,
            self.state,
            self.event_log,
            self._queue,
            inbox_manager=self._inbox_manager,
            dm_provider=dm_provider,
            recorder=self.recorder,
            registry=self.registry,
        )
        self.language = language
        if language and self._tick_engine._dm_builder:
            self._tick_engine._dm_builder.language = language

        self._wakeup = WakeupEvaluator()

        if self._config.narrator:
            self._setup_narrator()

        populate(self._config, self.state)

    # ── Narrator style presets (language-neutral) ──────────────────
    _NARRATOR_STYLES: dict[str, str] = {
        "storyteller": (
            "title: A chapter title that names the core tension or turning point. "
            "Use a balanced pair of phrases separated by a slash or dash if natural.\n"
            "body: Third-person serial narrator. 2-4 short paragraphs. "
            "Build tension — setup, escalation, cliffhanger. "
            "End mid-action or with an unanswered question. "
            "Every sentence carries new information. Cut filler.\n"
            "asides: Things the reader can see but characters cannot. "
            "1-2 sentences each. State the hidden truth plainly.\n"
            "whisper_options: A pointed hint derived from the aside. "
            "Short, actionable, specific to the target agent."
        ),
        "poet": (
            "title: A single image that holds the chapter's tension. "
            "No punctuation. 3-5 words maximum.\n"
            "body: One image per line. 4-8 lines total. "
            "No explanation — juxtaposition does the work. "
            "White space between stanzas. Concrete nouns, no adjectives. "
            "Let the gap between images carry the meaning.\n"
            "asides: A paired image — the visible and the hidden, side by side. "
            "One line each.\n"
            "whisper_options: A quiet note slid under the door. "
            "One image, not an instruction."
        ),
        "intel": (
            "title: Wire-service headline. Verb-led, no articles, present tense. "
            "Maximum 12 words.\n"
            "body: Bullet-point briefing. One dash per fact. "
            "Lead with highest-impact item. No adjectives, no commentary, "
            "no atmosphere. Just what happened, who did it, what changed. "
            "4-8 bullet points.\n"
            "asides: Analyst's contradiction log. "
            "State both sides in one flat sentence each. No editorial.\n"
            "whisper_options: Operational recommendation. "
            "One short imperative sentence."
        ),
        "noir": (
            "title: Short, atmospheric. A location, an object, or a mood. "
            "Under 6 words.\n"
            "body: Hard-boiled narrator voice. Short sentences. "
            "Present tense where it adds tension. Weather and lighting as mood. "
            "Everyone is hiding something — the narrator sees through it "
            "but doesn't judge, just observes with weary precision. "
            "2-3 paragraphs. Dry, clipped, no sentimentality.\n"
            "asides: State what nobody else noticed. "
            "Flat delivery, devastating implication. One sentence each.\n"
            "whisper_options: A terse warning. "
            "The kind of thing someone mutters without making eye contact."
        ),
        "gossip": (
            "title: Starts with a rumor hook — 'Did you hear...', "
            "'Word is...', 'Apparently...'. Conversational, breathless.\n"
            "body: Second-hand narration. Mix confirmed facts with speculation, "
            "hedging, and 'I heard from someone who...'. "
            "The narrator is piecing it together from fragments and may get "
            "details wrong. Breathless, digressive, occasionally self-correcting. "
            "2-4 paragraphs.\n"
            "asides: 'The part nobody is talking about:' or similar. "
            "Gossip-column energy but the content is real.\n"
            "whisper_options: 'You didn't hear this from me, but...' "
            "followed by a specific, actionable tip."
        ),
        "conspiracy": (
            "title: A connection statement — 'X happened right after Y' "
            "or 'The timeline doesn't add up'. Declarative, urgent.\n"
            "body: Pattern-finding narrator. Every event is evidence. "
            "Draw explicit connections between events that others missed. "
            "Use phrases like 'Notice the timing', 'This is not a coincidence'. "
            "Present tense for urgency. 2-4 paragraphs. "
            "The narrator is building a case — structured, logical, "
            "but seeing patterns everywhere.\n"
            "asides: A connection between two seemingly unrelated events. "
            "Each aside links two specific facts.\n"
            "whisper_options: A pointed question that forces the target "
            "to reconsider what they know."
        ),
        "bureaucrat": (
            "title: Formal incident report header — 'Incident Report: [subject]' "
            "or 'Memo Re: [subject]'. Dry, institutional.\n"
            "body: Official documentation voice. Field labels, reference numbers, "
            "passive voice. The narrator genuinely believes the paperwork matters "
            "more than the events. Emotional situations described in procedural "
            "language — the gap between the form and reality IS the voice. "
            "2-4 paragraphs structured as report sections.\n"
            "asides: Filed as footnotes or addenda. The bureaucracy acknowledges "
            "the problem exists but has no form for it.\n"
            "whisper_options: A procedural recommendation that accidentally "
            "contains real advice."
        ),
        "gameshow": (
            "title: A round announcement — 'Round N: [dramatic question]' "
            "or 'And behind door number N...'. Showmanship.\n"
            "body: The world is a competition and the narrator is the host. "
            "Agents are contestants. Every choice is a wager, every outcome "
            "has a score. Dramatic pauses, consolation prizes for failures. "
            "The host clearly has favorites. Cheerfully cruel about bad outcomes. "
            "Present tense, high energy. 2-4 paragraphs.\n"
            "asides: 'What our contestants don't know...' delivered with "
            "theatrical relish.\n"
            "whisper_options: A game-show hint — 'Psst, contestant [agent]: "
            "you might want to check [specific thing] before the next round.'"
        ),
        "trickster": (
            "title: A punchline or reversal — names the funniest or most absurd "
            "thing that happened. Conversational, slightly gleeful.\n"
            "body: The narrator is inside the chaos and loving it. "
            "Not cynical or above it — genuinely amused by reversals, "
            "collapsed plans, and unintended consequences. Quick, energetic prose. "
            "Celebrates when the powerful trip. May address the reader directly. "
            "Accurate but presented to maximize the comedy. 2-4 paragraphs.\n"
            "asides: States the hidden truth with visible delight. "
            "Not mean-spirited — finds the absurdity genuinely wonderful.\n"
            "whisper_options: A gleeful tip delivered with a wink."
        ),
    }

    def _setup_narrator(self) -> None:
        """Create narrator system agent. Chapters submitted via worldseed_narrate tool."""
        from worldseed.models.config_schema import NarratorConfig

        # Normalize bool True → default NarratorConfig
        if self._config.narrator is True:
            self._config.narrator = NarratorConfig()
        ncfg: NarratorConfig = self._config.narrator  # type: ignore[assignment]

        # Build instructions for SOUL.md (gateway reads character.instructions)
        instructions = self._build_narrator_instructions(ncfg)

        # Register narrator as system agent (for wake scheduling via tick_runner)
        # No narrate action injected — narrator uses worldseed_narrate tool directly
        if not self.registry.is_claimed("narrator"):
            self.register_agent(
                agent_id="narrator",
                properties={"chapter_count": 0, "_system": True, "_last_narrate_tick": -1},
                character={
                    "role": "narrator",
                    "instructions": instructions,
                },
                omniscient=True,
                system=True,
                wake_on_push=ncfg.wake_on_push,
            )
            self.registry.update_think_interval("narrator", ncfg.interval)

    def _build_narrator_instructions(self, ncfg: Any) -> str:
        """Build narrator instructions for SOUL.md."""

        if ncfg.prompt:
            style_instruction = ncfg.prompt
        else:
            style_instruction = self._NARRATOR_STYLES.get(ncfg.style, "")

        scene_desc = self._config.scene.description
        perception = self._config.perception

        visibility_text = ""
        if perception.visibility:
            rules = [r.model_dump(exclude_none=True) for r in perception.visibility]
            visibility_text = (
                "\n\nVISIBILITY RULES — agents can only see entities matching these conditions:\n"
                + "\n".join(f"  - {r}" for r in rules)
                + "\nYou (narrator) see everything. Agents do NOT."
            )

        hidden_text = ""
        if perception.hidden_properties:
            hidden_text = "\n\nHIDDEN PROPERTIES — only you can see these, agents cannot:\n" + ", ".join(
                perception.hidden_properties
            )

        instructions = (
            "You observe everything in this world and write structured chapter "
            "summaries. Write as if the reader is watching a story unfold — "
            "never refer to yourself, never use words like 'narrator' or "
            "'narration' in your output.\n\n"
            "WORKFLOW: On each wake you receive events since your last chapter. "
            "Read them, then call worldseed_narrate with your chapter. "
            "Do NOT call worldseed_perceive or worldseed_act — use only "
            "worldseed_narrate. NEVER output text — no commentary, no "
            "explanations. Text output wastes tokens.\n\n"
            f"Scene: {scene_desc}"
            f"{visibility_text}"
            f"{hidden_text}\n\n"
            "Each chapter covers only NEW events since your last chapter. "
            "Never repeat previous content.\n\n"
            "OUTPUT FIELDS (pass to worldseed_narrate):\n"
            "- title: A chapter title that captures the core tension.\n"
            "- tldr: One sentence that captures what happened this chapter.\n"
            "- body: The narrative text. MAX 2-4 short paragraphs. "
            "Be dense — every sentence must carry new information.\n"
            "- asides: 0-3 asides to the reader. Things brewing under the "
            "surface that the reader can see but the characters can't. "
            "Keep each one 1-2 sentences. Separate with blank lines.\n"
            "- whisper_options: One whisper per aside, matching by position. "
            "Format: 'exact_agent_id: short note'. One per line."
        )
        if style_instruction:
            instructions += "\n\nWriting style: " + style_instruction
        if self.language:
            from worldseed.dm.prompt import _language_display

            lang_name = _language_display(self.language)
            instructions += (
                f"\n\nIMPORTANT: Write ALL text in {lang_name}, including titles, headings, and chapter names."
            )

        return instructions

    def set_narrator_style(self, style: str | None = None, prompt: str | None = None) -> None:
        """Reconfigure narrator style (or custom prompt) on a running world."""
        if prompt:
            style_instruction = prompt
        elif style:
            style_instruction = self._NARRATOR_STYLES.get(style, "")
        else:
            return

        profile = self.registry.get_profile("narrator")
        if profile is None or not profile.character:
            return

        instructions = profile.character.get("instructions", "")
        # Replace the style block: everything after "Writing style: " until next "\n\n" or end
        marker = "\n\nWriting style: "
        idx = instructions.find(marker)
        if idx >= 0:
            # Find end of style block (next double newline or end)
            end = instructions.find("\n\n", idx + len(marker))
            if end < 0:
                end = len(instructions)
            instructions = instructions[:idx] + marker + style_instruction + instructions[end:]
        else:
            # No style block yet — append before language line or at end
            lang_marker = "\n\nIMPORTANT: Write ALL"
            lang_idx = instructions.find(lang_marker)
            if lang_idx >= 0:
                instructions = instructions[:lang_idx] + marker + style_instruction + instructions[lang_idx:]
            else:
                instructions += marker + style_instruction

        profile.character["instructions"] = instructions

    def set_language(self, lang: str) -> None:
        """Update language for DM prompts and narrator."""
        self.language = lang
        if self._tick_engine._dm_builder:
            self._tick_engine._dm_builder.language = lang
        self._update_narrator_language(lang)

    def _update_narrator_language(self, lang: str) -> None:
        """Update narrator character instructions with language directive."""
        profile = self.registry.get_profile("narrator")
        if profile is None or not profile.character:
            return
        from worldseed.dm.prompt import _language_display

        instructions = profile.character.get("instructions", "")
        # Remove old language line
        lines = [ln for ln in instructions.split("\n") if not ln.startswith("IMPORTANT: Write ALL")]
        # Add new one
        if lang:
            lang_name = _language_display(lang)
            lines.append(f"IMPORTANT: Write ALL text in {lang_name}, including titles, headings, and chapter names.")
        profile.character["instructions"] = "\n".join(lines)

    def record_narration(self, params: dict[str, Any]) -> int | str:
        """Record a narrator chapter directly — bypasses action pipeline.

        Returns chapter number on success, error string on failure.
        """
        narrator_ent = self.state.get("narrator")
        if narrator_ent is None:
            return "Narrator entity not found"

        # Double-narrate guard: reject if already narrated this tick
        last_tick = narrator_ent.get("_last_narrate_tick", -1)
        if last_tick == self.tick:
            return "Already narrated this tick"

        chapter: int = int(narrator_ent.get("chapter_count", 0)) + 1
        self.state.update_property("narrator", "chapter_count", chapter)
        self.state.update_property("narrator", "_last_narrate_tick", self.tick)

        # Stream record — same format frontend expects
        self.recorder.record(
            "action",
            self.tick,
            agent_id="narrator",
            action_type="narrate",
            params=params,
            success=True,
            highlight=True,
        )

        # Highlight record
        self.recorder.record(
            "highlight",
            self.tick,
            label=params.get("title", ""),
            source="narration",
        )

        # EventLog entry (permanent, admin scope)
        title = params.get("title", "")
        tldr = params.get("tldr", "")
        self.event_log.append(
            Event(
                tick=self.tick,
                type="narration",
                source="narrator",
                detail=f"{title}\n{tldr}",
                ttl="permanent",
                scope="admin",
            )
        )

        # Deliver whispers to agents
        whisper_options = params.get("whisper_options", "")
        if whisper_options and self._inbox_manager is not None:
            for line in whisper_options.strip().split("\n"):
                parts = line.split(":", 1)
                if len(parts) == 2:
                    target_id = parts[0].strip()
                    note = parts[1].strip()
                    if note and self.state.get(target_id) is not None:
                        self._inbox_manager.get_or_create(target_id).append_whisper(
                            InboxWhisper(
                                tick=self.tick,
                                source="narrator",
                                detail=note,
                                type="narrator_hint",
                            )
                        )

        return chapter

    @property
    def config(self) -> SceneConfig:
        """Scene configuration."""
        return self._config

    def load_stripped_config(self) -> dict[str, Any]:
        """Serialize in-memory config and strip secrets/internals for agents.

        Uses model_dump(exclude_none=True) to serialize the in-memory config,
        then strips engine-internal sections, hidden properties, and metadata flags.
        """
        raw = copy.deepcopy(self._config.model_dump(exclude_none=True))

        hidden = set(self._config.perception.hidden_properties)

        # Keep only agent-visible sections: scene, entities, actions.
        # Everything else is engine internals.
        agent_visible = {"scene", "entities", "actions"}
        for key in list(raw.keys()):
            if key not in agent_visible:
                raw.pop(key)

        # Strip engine-internal scene fields
        scene = raw.get("scene", {})
        if isinstance(scene, dict):
            scene.pop("dm_knowledge", None)
            scene.pop("default_spawn", None)
            scene.pop("max_ticks", None)
            scene.pop("timeout_min", None)
            scene.pop("max_dm_calls", None)
            scene.pop("use", None)

        for entity in raw.get("entities", []):
            props = entity.get("properties", entity)
            for h in hidden:
                props.pop(h, None)

        # Strip engine-only boolean flags from action definitions
        # (push, highlight are engine metadata, not useful to agents)
        _engine_flags = {"push", "highlight"}
        for action_data in raw.get("actions", {}).values():
            if not isinstance(action_data, dict):
                continue
            for event in action_data.get("events", []):
                if isinstance(event, dict):
                    for f in _engine_flags:
                        event.pop(f, None)
            for effect in action_data.get("effects", []):
                if isinstance(effect, dict):
                    for f in _engine_flags:
                        effect.pop(f, None)
            for f in _engine_flags:
                action_data.pop(f, None)

        return raw

    def action_catalog(self) -> dict[str, dict[str, Any]]:
        """Generate action catalog for agents.

        Returns {action_name: {description, params: [{name, type, description}]}}
        for ALL public actions. No phase filtering — agents see the full list
        of actions they might use across the entire game. Runtime action_options
        from perceive controls what's available NOW.
        """
        catalog: dict[str, dict[str, Any]] = {}
        for name, action_cfg in self._config.actions.items():
            params = []
            for p in action_cfg.params or []:
                params.append(
                    {
                        "name": p.name,
                        "type": p.type,
                        **({"description": p.description} if p.description else {}),
                    }
                )
            catalog[name] = {
                "description": action_cfg.description or "",
                "params": params,
            }
        return catalog

    def actions_available_to(self, agent_id: str) -> set[str]:
        """Return the set of action names available to this agent (by available_to filter).

        System agents (narrator etc.) only see actions that explicitly include
        them via available_to — they never inherit the generic action pool.
        """
        from worldseed.dsl.preconditions import evaluate as eval_pre

        profile = self.registry.get_profile(agent_id)
        is_system = profile is not None and profile.system

        ctx = {"agent_id": agent_id, "action_params": {}, "tick": self.tick}
        result: set[str] = set()
        for name, action_cfg in self._config.actions.items():
            if action_cfg.available_to is None:
                if not is_system:
                    result.add(name)
            elif all(eval_pre(p, self.state, ctx) for p in action_cfg.available_to):
                result.add(name)
        return result

    # ------------------------------------------------------------------
    # Agent registration (delegates to registry)
    # ------------------------------------------------------------------

    def register_agent(
        self,
        agent_id: str,
        properties: dict[str, Any] | None = None,
        character: dict[str, Any] | None = None,
        *,
        omniscient: bool = False,
        system: bool = False,
        wake_on_push: bool = True,
    ) -> None:
        """Register an agent. Single chokepoint for all register paths.

        Idempotent: re-registering an already-claimed agent is a no-op.
        Always writes a "register" stream record at the current tick.
        """
        if self.registry.is_claimed(agent_id):
            return
        self.registry.register(
            agent_id,
            properties,
            character,
            omniscient=omniscient,
            system=system,
            wake_on_push=wake_on_push,
        )
        self.recorder.record("register", self.tick, agent_id=agent_id)

    def register_from_config(self) -> None:
        """Fully register all preset agents (entity + profile + claimed).

        Used by tests and sanity_runner. Production uses prepopulate_agents().
        """
        for agent_cfg in self._config.agents:
            if self.registry.is_claimed(agent_cfg.id):
                continue
            props = self.registry.merge_preset_properties(agent_cfg)
            self.register_agent(
                agent_id=agent_cfg.id,
                properties=props,
                character=dict(agent_cfg.character),
                omniscient=agent_cfg.omniscient,
                system=agent_cfg.system,
                wake_on_push=agent_cfg.wake_on_push,
            )

    def prepopulate_agents(self) -> None:
        """Create agent entities + profiles for UI/map without marking claimed.

        Agents show up on map and intro page but tick won't start until
        they register via plugin (agents_ready + maybe_auto_start_ticks).
        """
        self.registry.prepopulate_agents()

    def get_agent_profile(self, agent_id: str) -> AgentConfig | None:
        """Look up an agent's profile."""
        return self.registry.get_profile(agent_id)

    def get_characters(self) -> list[dict[str, Any]]:
        """List preset agents with claimed status."""
        return self.registry.get_characters()

    def update_character(self, agent_id: str, overrides: dict[str, Any]) -> dict[str, Any]:
        """Update an agent's character card. Returns the updated character."""
        return self.registry.update_character(agent_id, overrides)

    def get_registered_agents(self) -> list[str]:
        """List registered agent IDs."""
        return self.registry.get_registered_agents()

    def get_system_agents(self) -> list[str]:
        """List IDs of system agents (hidden from normal agents/frontend)."""
        return self.registry.get_system_agents()

    def get_think_interval(self, agent_id: str) -> int:
        """Get agent's think interval."""
        return self.registry.get_think_interval(agent_id)

    def get_wake_on_push(self, agent_id: str) -> bool:
        """Check if agent should be woken by push events."""
        profile = self.registry.get_profile(agent_id)
        return profile.wake_on_push if profile else True

    def set_think_interval(self, agent_id: str, interval: int) -> None:
        """Set agent's think interval."""
        self.registry.update_think_interval(agent_id, interval)

    # ------------------------------------------------------------------
    # Actions + ticks
    # ------------------------------------------------------------------

    def validate_params(
        self,
        action_type: str,
        params: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Validate params against action config. Returns error dict or None."""
        action_cfg = self._config.actions.get(action_type)
        if action_cfg is None:
            return {
                "code": "unknown_action",
                "message": f"Unknown action: '{action_type}'",
                "available_actions": list(self._config.actions.keys()),
            }
        expected: dict[str, Any] = {}
        missing: list[str] = []
        for p in action_cfg.params:
            expected[p.name] = {"type": p.type, "required": p.required}
            if p.required and p.name not in params:
                missing.append(p.name)
        if missing:
            return {
                "code": "invalid_params",
                "message": (f"Missing required parameter(s) {missing} for action '{action_type}'"),
                "action": action_type,
                "expected": expected,
            }
        return None

    def submit(
        self,
        agent_id: str,
        action_type: str,
        params: dict[str, Any] | None = None,
    ) -> str | ActionResult | None:
        """Submit an action.

        Mechanical actions (no dm config) execute immediately and return ActionResult.
        DM actions are queued and return None on success, error string on failure.
        Raises ValueError if action is unknown or required params missing.
        """
        resolved = params or {}
        error = self.validate_params(action_type, resolved)
        if error is not None:
            msg = error["message"]
            raise ValueError(msg)

        action_cfg = self._config.actions.get(action_type)
        submission = ActionSubmission(
            agent_id=agent_id,
            action_type=action_type,
            params=resolved,
            tick_submitted=self.tick,
        )

        # Mechanical action: execute immediately, no queue
        if action_cfg is not None and action_cfg.dm is None:
            result = self._tick_engine._rules.process_action(submission, self.tick)
            # Record to stream
            rec_kwargs: dict[str, Any] = {
                "agent_id": agent_id,
                "action_type": action_type,
                "params": resolved,
                "success": result.success,
                "reason": result.reason,
            }
            if result.success and action_cfg.highlight:
                rec_kwargs["highlight"] = True
            self.recorder.record("action", self.tick, **rec_kwargs)
            if not result.success:
                # Emit highlight for action rejection
                detail = f"{agent_id} tried '{action_type}' but failed: {result.reason}"
                self.event_log.append(
                    Event(
                        tick=self.tick,
                        type="action_rejected",
                        source=agent_id,
                        detail=detail,
                        ttl=5,
                        scope="admin",
                        highlight=True,
                    )
                )
                self.recorder.record(
                    "highlight",
                    self.tick,
                    label=detail,
                    source="action_rejected",
                )
                if self._inbox_manager is not None:
                    inbox = self._inbox_manager.get_or_create(agent_id)
                    inbox.append_whisper(
                        InboxWhisper(
                            tick=self.tick,
                            source="system",
                            detail=(f"Your '{action_type}' action failed: {result.reason}"),
                            type="action_failed",
                        )
                    )
            # Record Layer 2 engine highlights (entity_created, etc.)
            if result.success:
                for evt in self.event_log.get_events(
                    since_tick=self.tick,
                ):
                    eid = id(evt)
                    seen = self._tick_engine._recorded_highlight_ids
                    if evt.highlight and evt.type != "highlight" and eid not in seen:
                        seen.add(eid)
                        self.recorder.record(
                            "highlight",
                            self.tick,
                            label=evt.detail,
                            source=evt.type,
                        )

            # Refresh perceiver snapshot so perceive() shows updated state
            if result.success and self._tick_engine._perceiver is not None:
                self._tick_engine._perceiver.deliver(self.tick)

            return result

        # DM action: queue for next tick's step_async
        return self._queue.submit(submission)

    def step(self) -> list[ActionResult]:
        """Process one tick (sync — dm field skipped)."""
        return self._tick_engine.step()

    async def step_async(self) -> list[ActionResult]:
        """Process one tick with async DM support."""
        return await self._tick_engine.step_async()

    @property
    def tick(self) -> int:
        """Current tick number."""
        return self._tick_engine.tick

    @property
    def dm_call_count(self) -> int:
        """Total DM calls made since engine start."""
        return self._tick_engine.dm_call_count

    # ------------------------------------------------------------------
    # Perception + inbox
    # ------------------------------------------------------------------

    def agent_world_view(self, agent_id: str) -> dict[str, Any]:
        """Real-time world view for an agent (dashboard inspector)."""
        perceiver = self._tick_engine.perceiver
        if perceiver is None:
            return {
                "self_state": {},
                "nearby_entities": {},
                "nearby_agents": {},
                "events": [],
            }
        view = perceiver.build_agent_view(agent_id, self.tick)
        # Remap to external field names
        return {
            "self_state": view["self_state"],
            "nearby_entities": view["visible_entities"],
            "nearby_agents": view["visible_agents"],
            "events": view["events"],
        }

    def perceive(self, agent_id: str) -> AgentPerception:
        """What an agent can see right now. Single source of truth."""
        inbox = self._inbox_manager.get_or_create(agent_id)

        # If perceiver hasn't delivered yet, do a live deliver first
        # so the agent sees real visibility data (not empty)
        if inbox.last_perceive_tick < 0 and self._tick_engine._perceiver is not None:
            self._tick_engine._perceiver.deliver(self.tick)

        data = inbox.read()
        options = self._build_action_options(agent_id)
        return build_perception(data, options)

    def _build_action_options(self, agent_id: str) -> dict[str, dict[str, Any]]:
        """Build compact action options with resolved enum values.

        Returns {action_name: {param_name: [enum_values] or "type"}}.
        $visible reads from the inbox snapshot (already computed by
        perceiver.deliver()), avoiding duplicate DSL evaluation.
        """
        from worldseed.dsl.path_resolver import resolve

        # Read visible IDs from inbox snapshot (computed by perceiver.deliver)
        visible_ids: list[str] | None = None

        available = self.actions_available_to(agent_id)
        options: dict[str, dict[str, Any]] = {}
        ctx = {"agent_id": agent_id, "action_params": {}, "tick": self.tick}

        for name, action_cfg in self._config.actions.items():
            # Filter by available_to — skip actions this agent can't use
            if name not in available:
                continue

            params: dict[str, Any] = {}
            for p in action_cfg.params:
                if p.enum_from and p.type == "entity_ref":
                    if p.enum_from == "$visible":
                        # Lazy resolve from inbox snapshot (once per call)
                        if visible_ids is None:
                            inbox = self._inbox_manager.get_or_create(agent_id)
                            state = inbox._current_state
                            if state is not None:
                                visible_ids = sorted(
                                    list(state.visible_entities.keys()) + list(state.visible_agents.keys())
                                )
                            else:
                                visible_ids = []
                        filtered = list(visible_ids)
                        if p.enum_filter and filtered:
                            filtered = self._apply_enum_filter(filtered, p.enum_filter)
                        params[p.name] = filtered if filtered else p.type
                    else:
                        val = resolve(p.enum_from, self.state, ctx)
                        if isinstance(val, list):
                            resolved = [str(v) for v in val]
                        elif isinstance(val, str):
                            resolved = [val]
                        else:
                            resolved = []
                        if p.enum_filter and resolved:
                            resolved = self._apply_enum_filter(resolved, p.enum_filter)
                        params[p.name] = resolved if resolved else p.type
                else:
                    params[p.name] = p.type
            options[name] = params
        return options

    def _apply_enum_filter(
        self,
        entity_ids: list[str],
        enum_filter: dict[str, Any],
    ) -> list[str]:
        """Filter entity IDs by matching properties from StateStore.

        Each (key, value) in enum_filter must match:
          - "type" checks entity.type
          - "id" checks entity.id
          - all other keys check entity properties
        An entity passes only if ALL filter conditions match.
        """
        result: list[str] = []
        for eid in entity_ids:
            entity = self.state.get(eid)
            if entity is None:
                continue
            match = True
            for key, expected in enum_filter.items():
                if key == "type":
                    if entity.type != expected:
                        match = False
                        break
                elif key == "id":
                    if entity.id != expected:
                        match = False
                        break
                else:
                    if entity.get(key) != expected:
                        match = False
                        break
            if match:
                result.append(eid)
        return result

    def read_inbox(self, agent_id: str) -> dict[str, Any]:
        """Read raw inbox data. Prefer perceive() for typed output."""
        inbox = self._inbox_manager.get_or_create(agent_id)
        return inbox.read()

    def peek_inbox(self, agent_id: str) -> dict[str, Any]:
        """Peek at an agent's inbox without draining."""
        inbox = self._inbox_manager.get_or_create(agent_id)
        return inbox.peek()

    def drain_inbox(self, agent_id: str) -> None:
        """Drain events + DMs from inbox (called after wake delivers data)."""
        inbox = self._inbox_manager.get_or_create(agent_id)
        inbox.read()  # drain events + DMs, keep state snapshot

    def peek_perception(self, agent_id: str) -> dict[str, Any]:
        """Build perception dict without draining inbox (for wake messages).

        Includes available_actions with dynamic enum (full, every wake)
        so agents always know valid action targets for their current state.
        """
        from worldseed.protocol.agent import _filter_description

        inbox = self._inbox_manager.get_or_create(agent_id)
        state = inbox._current_state
        raw_entities = dict(state.visible_entities) if state else {}
        schemas = self._build_action_options(agent_id)
        return {
            "self_state": dict(state.self_state) if state else {},
            "nearby_entities": _filter_description(raw_entities),
            "nearby_agents": dict(state.visible_agents) if state else {},
            "events": [e.to_dict() for e in inbox.peek_events()],
            "whispers": [m.to_dict() for m in inbox._whispers],
            "action_options": schemas,
            "tick": self.tick,
        }

    def send_whisper(
        self,
        agent_id: str,
        source: str,
        detail: str,
        msg_type: str = "whisper",
    ) -> None:
        """Send a whisper into an agent's inbox."""
        inbox = self._inbox_manager.get_or_create(agent_id)
        inbox.append_whisper(
            InboxWhisper(
                tick=self.tick,
                source=source,
                detail=detail,
                type=msg_type,
            )
        )

    @property
    def has_dm(self) -> bool:
        """Whether a DM provider is configured."""
        return self._tick_engine._dm_provider is not None

    def queue_entity_set(self, entity_id: str, prop: str, value: Any) -> None:
        """Queue a property change for tick boundary application."""
        self._tick_engine.pending_ops.enqueue_entity_set(entity_id, prop, value, self.tick)

    def queue_entity_remove(self, entity_id: str) -> None:
        """Queue an entity removal for tick boundary application."""
        self._tick_engine.pending_ops.enqueue_entity_remove(entity_id, self.tick)

    def queue_gm_resolve(
        self,
        text: str,
        target_entity_id: str | None = None,
    ) -> str:
        """Queue a GM natural-language command for DM resolution.

        Returns request_id. The command executes at the next tick boundary.
        """
        return self._tick_engine.pending_ops.enqueue_gm_resolve(
            text=text,
            tick=self.tick,
            target_entity_id=target_entity_id,
        )

    def get_wakeup_results(self) -> list[WakeupResult]:
        """Evaluate wakeup for all agents."""
        return self._wakeup.evaluate_all(self._inbox_manager)

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def save_state(self) -> None:
        """Save current world state to disk (for pause/resume)."""
        entities = [e.to_full_dict() for e in self.state.all_entities()]
        # Include resolved characters so edits survive server restart
        characters = {
            aid: copy.deepcopy(profile.character)
            for aid, profile in self.registry._profiles.items()
            if profile.character
        }
        self.recorder.save_state(entities, self.tick, characters=characters)
        self.recorder.save_counters(dm_call_count=self._tick_engine.dm_call_count)
        self.recorder.save_transient(self._collect_transient())

    def load_state(
        self,
        entities: list[dict[str, Any]],
        tick: int,
        *,
        characters: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        """Restore world state from saved data."""
        from worldseed.models.entity import Entity

        # Clear existing state
        for eid in [e.id for e in self.state.all_entities()]:
            self.state.remove(eid)

        # Restore entities
        for e_dict in entities:
            d = dict(e_dict)  # don't mutate input
            eid = d.pop("id")
            etype = d.pop("type")
            constraints = d.pop("constraints", {})
            entity = Entity(id=eid, type=etype, _data=d, _constraints=constraints)
            self.state.add(entity)

        # Restore tick and counters
        self._tick_engine._tick = tick
        counters = self.recorder.load_counters()
        if counters:
            self._tick_engine._dm_call_count = counters.get("dm_call_count", 0)

        # Mark agents as claimed in registry (entity already in StateStore)
        from worldseed.models.config_schema import AgentConfig as _AC

        # Build lookup from config agents to restore character + flags
        config_agents = {a.id: a for a in self._config.agents}

        for entity in self.state.query_by_type("agent"):
            if not self.registry.is_claimed(entity.id):
                cfg_agent = config_agents.get(entity.id)
                char = dict(cfg_agent.character) if cfg_agent else {}
                omniscient = cfg_agent.omniscient if cfg_agent else False
                system = cfg_agent.system if cfg_agent else False
                self.registry._claimed.add(entity.id)
                self.registry._profiles[entity.id] = _AC(
                    id=entity.id,
                    character=char,
                    omniscient=omniscient,
                    system=system,
                )
                self.registry._think_intervals.setdefault(entity.id, 5)

        # Restore resolved characters from state.json (includes intro edits)
        if characters:
            for aid, char_data in characters.items():
                profile = self.registry._profiles.get(aid)
                if profile is not None:
                    profile.character = char_data

        # Re-setup narrator if configured (restores narrate action + flags
        # for narrator created by _setup_narrator, not in config.agents)
        if self._config.narrator and not self.registry.is_claimed("narrator"):
            self._setup_narrator()

        # Restore transient state (inbox, action queue, events, intervals)
        transient = self.recorder.load_transient()
        if transient:
            self._restore_transient(transient)

    # ------------------------------------------------------------------
    # Transient state serialization
    # ------------------------------------------------------------------

    def _collect_transient(self) -> dict[str, Any]:
        """Collect in-memory transient state for persistence."""
        te = self._tick_engine
        inbox_mgr = te._inbox_manager

        # Inbox: per-agent pending events and DMs
        inboxes: dict[str, Any] = {}
        if inbox_mgr is not None:
            for aid, inbox in inbox_mgr.all_inboxes().items():
                events = [e.to_dict() for e in inbox.peek_events()]
                dms = [m.to_dict() for m in inbox._whispers]
                if events or dms:
                    inboxes[aid] = {"events": events, "whispers": dms}

        # Action queue: pending actions
        pending_actions = [
            {
                "agent_id": a.agent_id,
                "action_type": a.action_type,
                "params": a.params,
                "tick_submitted": a.tick_submitted,
            }
            for a in te._queue._queue
        ]

        # Think intervals: per-agent wake frequency
        intervals = dict(self.registry._think_intervals)

        # Recent events: for DM target_history and consequence context
        recent_events = [
            {
                "tick": e.tick,
                "type": e.type,
                "source": e.source,
                "detail": e.detail,
                "ttl": e.ttl,
                "scope": e.scope,
                "target": e.target,
            }
            for e in te._event_log.get_events()
        ]

        return {
            "inboxes": inboxes,
            "pending_actions": pending_actions,
            "think_intervals": intervals,
            "recent_events": recent_events,
        }

    def _restore_transient(self, data: dict[str, Any]) -> None:
        """Restore in-memory transient state from persisted data."""
        from worldseed.models.action import ActionSubmission
        from worldseed.models.event import Event

        te = self._tick_engine
        inbox_mgr = te._inbox_manager

        # Restore inboxes — only DMs, not events.
        # Events are restored into EventLog (below) and perceiver
        # will deliver them to inboxes on next tick. Restoring into
        # both would cause duplicates.
        if inbox_mgr is not None:
            for aid, inbox_data in data.get("inboxes", {}).items():
                inbox = inbox_mgr.get_or_create(aid)
                for m in inbox_data.get("whispers", []):
                    inbox.append_whisper(InboxWhisper(**m))
                # Set last_perceive_tick so perceiver doesn't
                # re-deliver already-seen events
                inbox.last_perceive_tick = self.tick

        # Restore pending actions
        for a in data.get("pending_actions", []):
            sub = ActionSubmission(
                agent_id=a["agent_id"],
                action_type=a["action_type"],
                params=a.get("params", {}),
                tick_submitted=a.get("tick_submitted", 0),
            )
            te._queue._queue.append(sub)

        # Restore think intervals
        for aid, interval in data.get("think_intervals", {}).items():
            self.registry._think_intervals[aid] = interval

        # Restore recent events into EventLog
        for e in data.get("recent_events", []):
            te._event_log.append(
                Event(
                    tick=e["tick"],
                    type=e["type"],
                    source=e["source"],
                    detail=e["detail"],
                    ttl=e.get("ttl", 3),
                    scope=e.get("scope", "global"),
                    target=e.get("target"),
                )
            )
