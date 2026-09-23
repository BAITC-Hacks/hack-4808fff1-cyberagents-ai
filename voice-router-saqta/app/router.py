from __future__ import annotations

import time
from typing import Iterable

from openai import OpenAI

from .config import OPENAI_API_KEY, ROUTER_MODEL, SNAPSHOT_DATE, CONFIDENCE_THRESHOLD
from .data_store import compact_scenario_catalog, scenario_map
from .schemas import DialogState, RouterDecision

VALID_IDS = set(scenario_map()) | {"SYS_OUT_OF_SCOPE", "SYS_UNCLEAR", "SYS_GOODBYE"}

ROUTER_SYSTEM_PROMPT = f"""
You are the routing layer of Saqta Insurance voice contact center.
Today inside this synthetic dataset is {SNAPSHOT_DATE}.
Your only job is to choose the correct scenario(s) for the client's CURRENT utterance using dialog context.
You are NOT an encoder intent classifier. Reason from meaning, boundaries and conversation state.

CRITICAL RULES:
1. Return every intent expressed in the current utterance. For multi-intent, preserve spoken order, except urgent scenarios must go first.
2. Use SYS_UNCLEAR when the message is genuinely vague (for example: 'I have a question about insurance'). Do not guess.
3. Use SYS_OUT_OF_SCOPE when the request is outside Saqta's offered insurance services (loans, weather, jobs, life insurance, etc.).
4. Use SYS_GOODBYE only when the client ends the conversation.
5. Respect every BOUNDARIES/not_this_if rule. They are more important than keyword overlap.
6. Distinguish especially:
   - SC11 accident happening right now vs SC12 past accident where culprit is insured by Saqta vs SC13 own CASCO damage claim.
   - SC17 claim status vs SC19 disagreement with decision/amount.
   - SC26 policy exists but document did not arrive vs SC30 money charged but policy was not issued.
   - SC21 booking a doctor vs SC22 checking medical coverage vs SC23 asking only for clinics.
   - SC25 policy validity vs SC27 renewal.
7. Russian, Kazakh and mixed-language speech are equally valid. Detect language as ru/kk/mixed.
8. If the client is merely answering a slot question for an active scenario, set is_continuation=true and keep that scenario.
9. Extract only slot values explicitly present in the current utterance. Do not invent values. Put values in normalized text when obvious.
10. Confidence should reflect routing certainty, not writing quality.
11. Keep reasons short and factual; never reveal hidden chain-of-thought.

SCENARIO CATALOG:
{compact_scenario_catalog()}
""".strip()


class LLMRouter:
    def __init__(self, model: str = ROUTER_MODEL):
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not set. Copy .env.example to .env and add the key.")
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        self.model = model

    def route(self, text: str, state: DialogState | None = None) -> tuple[RouterDecision, int]:
        state = state or DialogState(session_id="eval")
        state_summary = {
            "language": state.language,
            "active_scenarios": state.active_scenarios,
            "scenario_stack": state.scenario_stack,
            "known_slots": state.slots,
            "recent_history": state.history[-6:],
        }
        started = time.perf_counter()
        response = self.client.responses.parse(
            model=self.model,
            input=[
                {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"DIALOG_STATE:\n{state_summary}\n\nCURRENT_UTTERANCE:\n{text}",
                },
            ],
            text_format=RouterDecision,
        )
        elapsed = round((time.perf_counter() - started) * 1000)
        decision = response.output_parsed
        if decision is None:
            raise RuntimeError("Router returned no parsed decision")
        self._validate_and_clean(decision)
        return decision, elapsed

    @staticmethod
    def _validate_and_clean(decision: RouterDecision) -> None:
        decision.scenarios = [x for x in decision.scenarios if x.scenario_id in VALID_IDS]
        decision.alternatives = [x for x in decision.alternatives if x.scenario_id in VALID_IDS]
        if not decision.scenarios:
            from .schemas import RouteCandidate
            decision.scenarios = [RouteCandidate(scenario_id="SYS_UNCLEAR", confidence=1.0, reason="No valid route returned")]


def accepted_ids(decision: RouterDecision, threshold: float = CONFIDENCE_THRESHOLD) -> list[str]:
    """Decision policy for the interactive demo.

    System intents are accepted directly. Business routes below the threshold become
    SYS_UNCLEAR instead of silently guessing.
    """
    primary = decision.scenarios[0]
    if primary.scenario_id.startswith("SYS_"):
        return [x.scenario_id for x in decision.scenarios]
    accepted = [x.scenario_id for x in decision.scenarios if x.confidence >= threshold]
    return accepted or ["SYS_UNCLEAR"]
