from __future__ import annotations

from .data_store import scenario_map, slot_map
from .schemas import DialogState, RouterDecision


def _slot_dict(decision: RouterDecision) -> dict[str, str]:
    return {s.name: s.value for s in decision.slots}


# Normalizes common LLM slot-name variants into canonical dataset slot names.
SLOT_ALIASES = {
    "SC01": {
        "city": "region",
        "driver_iin": "drivers_iin",
        "driver": "drivers_iin",
    },
    "SC06": {
        "destination": "trip_country",
        "country": "trip_country",
    },
}


def build_reply(
    decision: RouterDecision,
    accepted: list[str],
    state: DialogState,
) -> str:
    """Deterministic response layer grounded in scenarios.json and slots.json."""

    # ---------------------------------------------------------
    # Language
    # ---------------------------------------------------------
    lang = (
        decision.language
        if decision.language in {"ru", "kk"}
        else state.language
    )
    state.language = lang

    # ---------------------------------------------------------
    # Extract and normalize slots returned by the LLM router
    # ---------------------------------------------------------
    extracted = _slot_dict(decision)

    if accepted and not accepted[0].startswith("SYS_"):
        current_scenario_id = accepted[0]
        aliases = SLOT_ALIASES.get(current_scenario_id, {})

        extracted = {
            aliases.get(key, key): value
            for key, value in extracted.items()
        }

    # ---------------------------------------------------------
    # Scenario switch
    #
    # Do not allow slots from the previous scenario to pollute
    # a newly selected scenario.
    # ---------------------------------------------------------
    if accepted and not accepted[0].startswith("SYS_"):
        new_scenario_id = accepted[0]
        new_scenario = scenario_map()[new_scenario_id]

        relevant_slots = set(
            new_scenario.get("slots", {}).get("required", [])
            + new_scenario.get("slots", {}).get("optional", [])
        )

        scenario_changed = (
            bool(state.active_scenarios)
            and state.active_scenarios[0] != new_scenario_id
            and not decision.is_continuation
        )

        if scenario_changed:
            state.slots = {
                key: value
                for key, value in state.slots.items()
                if key in relevant_slots and str(value).strip()
            }

    # ---------------------------------------------------------
    # Store only meaningful values.
    #
    # An empty string must NOT count as a completed slot.
    # ---------------------------------------------------------
    state.slots.update(
        {
            key: value
            for key, value in extracted.items()
            if str(value).strip()
        }
    )

    # ---------------------------------------------------------
    # System routes
    # ---------------------------------------------------------
    if accepted == ["SYS_OUT_OF_SCOPE"]:
        if lang == "ru":
            return (
                "С этим я не помогу. Могу помочь со страхованием "
                "авто, здоровья, жилья и поездок."
            )

        return (
            "Бұл сұрақ бойынша көмектесе алмаймын. "
            "Көлік, денсаулық, тұрғын үй және сапар "
            "сақтандыруы бойынша көмектесемін."
        )

    if accepted == ["SYS_GOODBYE"]:
        if lang == "ru":
            return "Спасибо за обращение! Хорошего дня."

        return "Хабарласқаныңызға рақмет! Күніңіз сәтті өтсін."

    if accepted == ["SYS_UNCLEAR"]:
        alternatives = [
            item.scenario_id
            for item in decision.alternatives[:2]
        ]

        if alternatives:
            names = [
                scenario_map()
                .get(scenario_id, {})
                .get("name", scenario_id)
                for scenario_id in alternatives
            ]

            if lang == "ru":
                return (
                    "Уточните, пожалуйста: речь про "
                    + " или ".join(names)
                    + "?"
                )

            return (
                "Нақтылап жіберіңізші, "
                "қай мәселе туралы айтып тұрсыз?"
            )

        if lang == "ru":
            return (
                "Уточните, пожалуйста, что именно вы хотите "
                "сделать со страховкой?"
            )

        return (
            "Нақтылап жіберіңізші, сақтандыру бойынша "
            "не істегіңіз келеді?"
        )

    # ---------------------------------------------------------
    # Safety fallback
    # ---------------------------------------------------------
    if not accepted:
        if lang == "ru":
            return "Уточните, пожалуйста, ваш запрос."

        return "Сұрағыңызды нақтылап жіберіңізші."

    # ---------------------------------------------------------
    # Business scenario
    # ---------------------------------------------------------
    scenario_id = accepted[0]
    scenario = scenario_map().get(scenario_id)

    if not scenario:
        if lang == "ru":
            return "Не удалось определить сценарий. Уточните запрос."

        return "Сценарий анықталмады. Сұрағыңызды нақтылаңыз."

    state.active_scenarios = accepted

    # ---------------------------------------------------------
    # Required slots
    # ---------------------------------------------------------
    required = scenario.get("slots", {}).get("required", [])

    missing = [
        name
        for name in required
        if not str(state.slots.get(name, "")).strip()
    ]

    # Ask only for the first missing required slot.
    if missing:
        missing_slot = missing[0]

        prompt = (
            slot_map()
            .get(missing_slot, {})
            .get("prompt", {})
            .get(lang)
        )

        if prompt:
            return prompt

        if lang == "ru":
            return f"Уточните, пожалуйста: {missing_slot}."

        return f"Нақтылап жіберіңізші: {missing_slot}."

    # ---------------------------------------------------------
    # Scenario opening / success response
    # ---------------------------------------------------------
    opening = (
        scenario
        .get("responses", {})
        .get(lang, {})
        .get("opening")
    )

    if opening:
        return opening

    return "Чем ещё помочь?" if lang == "ru" else "Тағы қалай көмектесе аламын?"