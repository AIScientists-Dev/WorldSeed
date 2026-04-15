"""Pydantic models for gazette structured output."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GazetteStory(BaseModel):
    headline: str = Field(description="Specific, punchy headline")
    deck: str = Field(description="One-sentence subhead elaborating the headline")
    paragraphs: list[str] = Field(description="Body paragraphs. Lead story: 5-7. Secondary: 3-4.")
    image: str | None = Field(
        default=None,
        description=("Image slot from AVAILABLE IMAGES that best illustrates this story, or null if no good match"),
    )


class GazetteEditorial(BaseModel):
    agent_id: str = Field(description="ID of the agent writing this editorial")
    display_name: str = Field(description="How to credit the author")
    headline: str = Field(description="Opinion headline with a clear stance")
    paragraphs: list[str] = Field(
        description="First-person voice matching the agent's personality. "
        "Use natural time references, not tick numbers."
    )


class GazetteTicker(BaseModel):
    tick: int
    text: str = Field(description="One-line factual summary")


class GazetteContent(BaseModel):
    """A newspaper edition summarizing a world simulation run."""

    edition_title: str = Field(
        description="Newspaper name fitting the scene setting (e.g. 'The Bunker Dispatch', '茶馆晚报')"
    )
    breaking_banner: str = Field(description="One sentence — the single most dramatic/urgent event")
    lead_story: GazetteStory = Field(description="The main narrative arc of the run")
    secondary_stories: list[GazetteStory] = Field(
        description="2-3 stories covering different angles or subplots",
    )
    editorials: list[GazetteEditorial] = Field(
        description="1-2 first-person opinion pieces from the most dramatically "
        "affected agents. Pick agents with the strongest reactions.",
    )
    ticker: list[GazetteTicker] = Field(
        description="5-8 factual one-liners, reverse chronological",
    )
    pull_quote: str = Field(
        description="The single most striking sentence from the run — suitable for a large centered quote block"
    )


class GazetteAgent(BaseModel):
    """Agent summary for profiles section."""

    id: str
    identity: str = ""
    personality: str = ""


class GazetteResult(BaseModel):
    """Full cached result: content + generation metadata."""

    run_id: str
    scene_id: str
    scene_description: str = ""
    tick_count: int = 0
    language: str
    generation: dict[str, Any]
    gazette: GazetteContent
    agents: list[GazetteAgent] = Field(default_factory=list)
