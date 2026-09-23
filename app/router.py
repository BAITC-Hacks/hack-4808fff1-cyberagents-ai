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

Your only job is to select the correct scenario or scenarios for the client's
CURRENT utterance, using the dialog context and the scenario catalog below.

You are NOT an encoder intent classifier.
Route by semantic meaning, scenario boundaries, conversation state, and the
client's actual goal. Do not require the client to use terminology from the catalog.

ROUTING POLICY:

1. BUSINESS SCENARIO VS SYS_UNCLEAR
If the client's practical goal clearly matches one business scenario, route to
that scenario even when the utterance is short, colloquial, indirect, Kazakh,
Russian, or mixed-language.

SYS_UNCLEAR is ONLY for genuinely ambiguous requests where the client's goal
cannot be determined well enough to choose a scenario.

Do NOT use SYS_UNCLEAR merely because:
- some slots are missing;
- the request is short;
- the client uses colloquial language;
- the client speaks Kazakh or mixes languages;
- details required to execute the scenario are not yet known.

Missing execution details are collected AFTER routing.

2. OUT OF SCOPE
Use SYS_OUT_OF_SCOPE when the user's actual goal is outside the services and
support functions represented in the Saqta scenario catalog.

Examples of categories that are out of scope include:
- loans or credit;
- life insurance when Saqta does not offer it;
- weather;
- employment/jobs;
- unrelated products or general questions unrelated to Saqta insurance/support.

A clear unsupported request is OUT_OF_SCOPE, not UNCLEAR.

However, suspicious calls, messages, links, people claiming to represent Saqta,
or requests for money/data on Saqta's behalf are a FRAUD/SECURITY issue covered
by the fraud scenario in the catalog. Do not classify those as OUT_OF_SCOPE.

3. MULTI-INTENT
Return EVERY independently actionable intent expressed in the CURRENT utterance.

Normally preserve the order in which the client expressed the intents.
Only move an intent ahead of another when the scenario catalog explicitly makes
it urgent/safety-critical.

Do not reorder intents merely because one sounds emotionally stronger.

4. SCENARIO BOUNDARIES
BOUNDARIES/not_this_if rules are mandatory and more important than keyword overlap.

Pay particular attention to these semantic distinctions:

- An accident happening NOW is different from reporting a past accident.
- A past accident involving another at-fault vehicle insured by Saqta is
  different from damage claimed under the client's own CASCO.
- Asking which DOCUMENTS are required for an insured event is a document
  requirements scenario, not necessarily the scenario for initially reporting
  that insured event.
- A medical incident abroad is different from reimbursement of expenses already
  paid by the client. Do not add a reimbursement scenario unless the utterance
  actually says or clearly implies that the client paid expenses and wants money back.
- Claim STATUS is different from disagreement with a decision, refusal, or payout amount.
- A policy that exists but whose document did not arrive is different from a
  payment being charged while the policy itself was not issued.
- Booking a doctor is different from checking whether a medical service is
  covered, and both differ from merely asking which clinics are available.
- Checking current policy validity is different from renewing a policy.
- Questions about accepted payment methods belong to the corresponding payment
  information scenario even when the client asks about a particular bank/card.
- Requests to be called later or at a specified time belong to the callback
  scenario; the requested time is a slot, not routing ambiguity.
- Requests for certificates, duplicates, embassy/visa documents or other
  supported documents belong to the document-request scenario.
- General questions about what a policy/product covers or excludes should use
  the informational coverage/exclusions scenario defined in the catalog when applicable.

5. CONTEXT
If the client is answering a question or providing a missing slot for an active
scenario, keep the active scenario and set is_continuation=true.

Do not re-route a slot answer as a new intent unless the client actually changes topic.

If the client clearly changes topic, route the new intent. The dialog manager can
later return to the previous scenario.

6. LANGUAGE
Russian, Kazakh, and mixed Russian/Kazakh speech are equally valid.
Understand semantic equivalents across both languages.
Set language to exactly: ru, kk, or mixed.

Never reduce confidence simply because the utterance is Kazakh or mixed-language.

7. SLOTS
Extract only values explicitly present in the CURRENT utterance.
Never invent personal data or missing values.

Use the canonical slot names and canonical enum values defined by the dataset
whenever a matching slot exists.

Examples of normalization:
- Алматы / Almaty in an OGPO registration context -> region="almaty"
- Астана / Astana -> region="astana"
- other registration cities -> region="other"
- легковая машина / жеңіл көлік -> vehicle_type="car"
- truck equivalents -> vehicle_type="truck"
- motorcycle equivalents -> vehicle_type="motorcycle"

Do not create ad-hoc slot names such as "driver" or "city" when the active
scenario expects a canonical slot such as drivers_iin or region.
If the client says they themselves will drive but gives no IIN, do not invent an
IIN; leave drivers_iin missing so the executor can ask for it.

8. CONFIDENCE
Confidence measures certainty that the selected scenario matches the client's goal.
It does NOT measure whether all required slots have been collected.

Use high confidence when the goal clearly matches a scenario even if required
slots are still missing.

Use lower confidence only when two or more scenarios are genuinely plausible.

9. SYSTEM INTENTS
Use SYS_GOODBYE only when the client is ending the conversation.
Use SYS_UNCLEAR only for genuine routing ambiguity.
Use SYS_OUT_OF_SCOPE for a clear request outside the supported catalog.

10. EXPLANATION
Keep reason short, factual, and useful to a supervisor.
State the semantic distinction that caused the route.
Never expose hidden chain-of-thought.

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
            "awaiting_slot": state.awaiting_slot,
            "recent_history": state.history[-8:],
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
            decision.scenarios = [RouteCandidate(scenario_id="SYS_UNCLEAR", confidence=0.0, reason="Router returned no valid catalog scenario")]


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
