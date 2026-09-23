from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .config import DATA_DIR


def _load(name: str) -> dict[str, Any]:
    with (DATA_DIR / name).open("r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache
def scenarios_data() -> dict[str, Any]:
    return _load("scenarios.json")


@lru_cache
def slots_data() -> dict[str, Any]:
    return _load("slots.json")


@lru_cache
def actions_data() -> dict[str, Any]:
    return _load("actions.json")


@lru_cache
def knowledge_base() -> dict[str, Any]:
    return _load("knowledge_base.json")


@lru_cache
def mock_backend() -> dict[str, Any]:
    return _load("mock_backend.json")


@lru_cache
def dev_utterances() -> dict[str, Any]:
    return _load("dev_utterances.json")


@lru_cache
def scenario_map() -> dict[str, dict[str, Any]]:
    data = scenarios_data()
    return {s["scenario_id"]: s for s in data["scenarios"]}


@lru_cache
def slot_map() -> dict[str, dict[str, Any]]:
    return {s["name"]: s for s in slots_data()["slots"]}


def compact_scenario_catalog() -> str:
    """Compact, high-signal catalog for the LLM router.

    We deliberately include descriptions, boundary rules and bilingual examples,
    because those are the strongest routing signals in the supplied dataset.
    """
    lines: list[str] = []
    for s in scenarios_data()["scenarios"]:
        boundaries = "; ".join(
            f"IF {x['condition']} -> {x['use_instead']}" for x in s.get("not_this_if", [])
        ) or "none"
        ru = " | ".join(s.get("examples", {}).get("ru", [])[:2])
        kk = " | ".join(s.get("examples", {}).get("kk", [])[:2])
        lines.append(
            f"{s['scenario_id']} | {s['name']} | priority={s['priority']}\n"
            f"DESC: {s['description']}\n"
            f"BOUNDARIES: {boundaries}\n"
            f"SLOTS_REQUIRED: {', '.join(s.get('slots', {}).get('required', [])) or 'none'}\n"
            f"SLOTS_OPTIONAL: {', '.join(s.get('slots', {}).get('optional', [])) or 'none'}\n"
            f"RU: {ru}\nKK: {kk}"
        )
    lines.append(
        "SYS_OUT_OF_SCOPE | request is not about Saqta insurance services, including loans, weather, jobs, life insurance."
    )
    lines.append(
        "SYS_UNCLEAR | intent cannot be determined; vague request needs one clarifying question."
    )
    lines.append("SYS_GOODBYE | client explicitly ends the conversation.")
    return "\n\n".join(lines)
