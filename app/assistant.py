from __future__ import annotations

import re

from .data_store import scenario_map, slot_map
from .executor import execute_scenario
from .schemas import DialogState, RouterDecision


def _slot_dict(decision: RouterDecision) -> dict[str, str]:
    return {s.name: s.value.strip() for s in decision.slots if s.value and s.value.strip()}


def _choose_reply_language(decision: RouterDecision, state: DialogState) -> str:
    if decision.language in {"ru", "kk"}:
        return decision.language
    return state.language if state.language in {"ru", "kk"} else "ru"


def _continuation_value(slot: str, text: str) -> str:
    value = text.strip().strip(" .,!?:;\"")
    low = value.lower()
    if slot == "region":
        if "алмат" in low:
            return "almaty"
        if "астан" in low:
            return "astana"
        return "other"
    if slot == "vehicle_type":
        if any(x in low for x in ("груз", "жүк", "truck")):
            return "truck"
        if any(x in low for x in ("мото", "motorcycle")):
            return "motorcycle"
        if any(x in low for x in ("легков", "жеңіл", "car", "машин")):
            return "car"
    if slot in {"travelers_count", "traveler_max_age", "employees_count", "car_year", "sum_insured", "car_value"}:
        m = re.search(r"\d+", value.replace(" ", ""))
        return m.group(0) if m else value
    if slot in {"phone", "iin", "drivers_iin", "new_driver_iin"}:
        digits = re.sub(r"\D", "", value)
        if slot == "phone" and len(digits) == 11 and digits[0] in "78":
            return "+7" + digits[1:]
        return digits or value
    return value


def build_reply(
    decision: RouterDecision,
    accepted: list[str],
    state: DialogState,
    current_text: str = "",
) -> tuple[str, str, dict | None]:
    lang = _choose_reply_language(decision, state)
    state.language = lang

    if accepted == ["SYS_OUT_OF_SCOPE"]:
        return (
            "С этим я не помогу. Могу помочь со страхованием авто, здоровья, жилья и поездок."
            if lang == "ru"
            else "Бұл сұрақ бойынша көмектесе алмаймын. Көлік, денсаулық, тұрғын үй және сапар сақтандыруы бойынша көмектесемін.",
            lang,
            None,
        )
    if accepted == ["SYS_GOODBYE"]:
        return (
            "Спасибо за обращение! Хорошего дня."
            if lang == "ru"
            else "Хабарласқаныңызға рақмет! Күніңіз сәтті өтсін.",
            lang,
            None,
        )
    if accepted == ["SYS_UNCLEAR"]:
        return (
            "Уточните, пожалуйста, что именно вы хотите сделать со страховкой?"
            if lang == "ru"
            else "Нақтылап жіберіңізші, сақтандыру бойынша не істегіңіз келеді?",
            lang,
            {"queue": "operator_general", "simulated": True, "reason": "low_confidence"}
            if len(state.history) >= 6
            else None,
        )

    scenario_id = accepted[0]
    scenario = scenario_map()[scenario_id]

    previous = state.active_scenarios[0] if state.active_scenarios else None
    if previous and previous != scenario_id and not decision.is_continuation:
        if previous not in state.scenario_stack:
            state.scenario_stack.append(previous)
        relevant = set(
            scenario.get("slots", {}).get("required", [])
            + scenario.get("slots", {}).get("optional", [])
        )
        state.slots = {
            k: v for k, v in state.slots.items()
            if k in relevant and str(v).strip()
        }
        state.awaiting_slot = None

    state.active_scenarios = accepted
    relevant = set(
        scenario.get("slots", {}).get("required", [])
        + scenario.get("slots", {}).get("optional", [])
    )
    extracted = {
        k: v for k, v in _slot_dict(decision).items()
        if k in relevant
    }

    if (
        decision.is_continuation
        and state.awaiting_slot
        and state.awaiting_slot in relevant
        and state.awaiting_slot not in extracted
        and current_text.strip()
    ):
        extracted[state.awaiting_slot] = _continuation_value(
            state.awaiting_slot,
            current_text,
        )

    state.slots.update(extracted)

    required = scenario.get("slots", {}).get("required", [])
    missing = [
        name for name in required
        if not str(state.slots.get(name, "")).strip()
    ]
    if missing:
        state.awaiting_slot = missing[0]
        prompt = slot_map().get(missing[0], {}).get("prompt", {}).get(lang)
        if prompt:
            return prompt, lang, None

    state.awaiting_slot = None
    executed, handoff = execute_scenario(scenario_id, state.slots, lang)
    if executed:
        return executed, lang, handoff

    opening = (
        scenario.get("responses", {}).get(lang, {}).get("opening")
        or scenario.get("responses", {}).get("ru", {}).get("opening")
    )
    return (
        opening or ("Чем ещё помочь?" if lang == "ru" else "Тағы қалай көмектесейін?"),
        lang,
        handoff,
    )
