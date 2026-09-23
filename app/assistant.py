from __future__ import annotations

from .data_store import scenario_map, slot_map
from .schemas import DialogState, RouterDecision


def _slot_dict(decision: RouterDecision) -> dict[str, str]:
    return {s.name: s.value for s in decision.slots}


def build_reply(decision: RouterDecision, accepted: list[str], state: DialogState) -> str:
    """Early MVP response layer.

    It is intentionally deterministic and grounded in scenarios.json. The next project
    milestone replaces this with the full scenario executor + mock actions.
    """
    lang = decision.language if decision.language in {"ru", "kk"} else state.language
    state.language = lang
    extracted = _slot_dict(decision)
    state.slots.update(extracted)

    if accepted == ["SYS_OUT_OF_SCOPE"]:
        return (
            "С этим я не помогу. Могу помочь со страхованием авто, здоровья, жилья и поездок."
            if lang == "ru"
            else "Бұл сұрақ бойынша көмектесе алмаймын. Көлік, денсаулық, тұрғын үй және сапар сақтандыруы бойынша көмектесемін."
        )
    if accepted == ["SYS_GOODBYE"]:
        return "Спасибо за обращение! Хорошего дня." if lang == "ru" else "Хабарласқаныңызға рақмет! Күніңіз сәтті өтсін."
    if accepted == ["SYS_UNCLEAR"]:
        alts = [a.scenario_id for a in decision.alternatives[:2]]
        if alts:
            names = [scenario_map().get(x, {}).get("name", x) for x in alts]
            joined = " или ".join(names)
            return f"Уточните, пожалуйста: речь про {joined}?" if lang == "ru" else "Нақтылап жіберіңізші, қай мәселе туралы айтып тұрсыз?"
        return "Уточните, пожалуйста, что именно вы хотите сделать со страховкой?" if lang == "ru" else "Нақтылап жіберіңізші, сақтандыру бойынша не істегіңіз келеді?"

    scenario_id = accepted[0]
    scenario = scenario_map()[scenario_id]
    state.active_scenarios = accepted
    required = scenario.get("slots", {}).get("required", [])
    missing = [name for name in required if name not in state.slots]
    if missing:
        prompt = slot_map().get(missing[0], {}).get("prompt", {}).get(lang)
        if prompt:
            return prompt
    return scenario.get("responses", {}).get(lang, {}).get("opening", "Чем ещё помочь?")
