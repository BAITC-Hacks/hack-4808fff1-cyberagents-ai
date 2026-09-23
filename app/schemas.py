from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field

Language = Literal["ru", "kk", "mixed"]


class RouteCandidate(BaseModel):
    scenario_id: str
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


class AlternativeCandidate(BaseModel):
    scenario_id: str
    confidence: float = Field(ge=0.0, le=1.0)


class ExtractedSlot(BaseModel):
    name: str
    value: str


class RouterDecision(BaseModel):
    scenarios: list[RouteCandidate]
    alternatives: list[AlternativeCandidate]
    language: Language
    slots: list[ExtractedSlot]
    is_continuation: bool


class DialogState(BaseModel):
    session_id: str
    language: Language = "ru"
    active_scenarios: list[str] = Field(default_factory=list)
    scenario_stack: list[str] = Field(default_factory=list)
    slots: dict[str, str] = Field(default_factory=dict)
    history: list[dict[str, str]] = Field(default_factory=list)
    awaiting_slot: str | None = None


class RouteRequest(BaseModel):
    session_id: str = "demo"
    text: str


class RouteResponse(BaseModel):
    decision: RouterDecision
    accepted_scenarios: list[str]
    latency_ms: dict[str, int]


class ChatResponse(BaseModel):
    session_id: str
    transcript: str
    reply: str
    language: Language
    scenarios: list[RouteCandidate]
    alternatives: list[AlternativeCandidate]
    accepted_scenarios: list[str] = Field(default_factory=list)
    slots: dict[str, str]
    reason: str
    handoff: dict | None = None
    latency_ms: dict[str, int]
