"""Request/response models for the HTTP API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class RegisterRequest(BaseModel):
    mode: Literal["claim", "create"]
    agent_id: str
    template: str | None = None
    character: dict[str, Any] = {}


class ActRequest(BaseModel):
    token: str | None = None
    agent_id: str | None = None
    action: str
    params: dict[str, Any] = {}
    think_interval: int | None = None


class ActResponse(BaseModel):
    queued: bool
    tick: int


class NotifyRequest(BaseModel):
    agent_id: str


class WhisperRequest(BaseModel):
    agent_id: str
    message: str


class EntitySetRequest(BaseModel):
    entity_id: str
    property: str
    value: Any


class EntityRemoveRequest(BaseModel):
    entity_id: str


class TickIntervalRequest(BaseModel):
    interval: float


class GMResolveRequest(BaseModel):
    text: str
    target_entity_id: str | None = None


class ConfigReloadRequest(BaseModel):
    config_path: str
