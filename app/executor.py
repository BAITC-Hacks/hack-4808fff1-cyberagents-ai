from __future__ import annotations

from datetime import date, datetime
from typing import Any

from .data_store import knowledge_base, mock_backend, scenario_map


def _money(value: int | float) -> str:
    return f"{int(round(value)):,}".replace(",", " ") + " ₸"


def _to_int(value: Any) -> int:
    s = str(value).strip().replace(" ", "").replace("₸", "")
    return int(float(s))


def _parse_date(value: str) -> date:
    return datetime.fromisoformat(value[:10]).date()


def _lang_text(lang: str, ru: str, kk: str) -> str:
    return kk if lang == "kk" else ru


def _find_policy(slots: dict[str, str]) -> dict[str, Any] | None:
    number = slots.get("policy_number", "").strip()
    plate = slots.get("vehicle_plate", "").strip().upper()
    for policy in mock_backend().get("policies", []):
        if number and policy.get("policy_number") == number:
            return policy
        if plate and str(policy.get("details", {}).get("vehicle_plate", "")).upper() == plate:
            return policy
    return None


def _find_claim(slots: dict[str, str]) -> dict[str, Any] | None:
    number = slots.get("claim_number", "").strip()
    for claim in mock_backend().get("claims", []):
        if number and claim.get("claim_number") == number:
            return claim
    return None


def _ogpo_quote(slots: dict[str, str]) -> int:
    kb = knowledge_base()["products"]["ogpo"]["pricing"]
    region = slots["region"].strip().lower()
    vehicle_type = slots["vehicle_type"].strip().lower()
    drivers = [x.strip() for x in slots["drivers_iin"].replace(";", ",").split(",") if x.strip()]
    client_classes = {c["iin"]: c.get("bm_class", "3") for c in mock_backend().get("clients", [])}
    order = knowledge_base()["bonus_malus"]["classes"]
    classes = [client_classes.get(iin, mock_backend().get("defaults", {}).get("unknown_iin_bm_class", "3")) for iin in drivers]
    worst = min(classes, key=lambda c: order.index(c)) if classes else "3"
    base = kb["base_by_region_kzt"].get(region, kb["base_by_region_kzt"]["other"])
    vehicle_coef = kb["vehicle_type_coef"].get(vehicle_type, 1.0)
    bm_coef = kb["bm_coef"].get(str(worst), 1.0)
    term = str(slots.get("term_months", "12"))
    term_coef = kb["term_coef"].get(term, 1.0)
    return round(base * vehicle_coef * bm_coef * term_coef)


def _travel_quote(slots: dict[str, str]) -> tuple[int, str, str]:
    product = knowledge_base()["products"]["travel"]
    country = slots["trip_country"].strip().lower()
    if country in {"usa", "united states", "сша", "canada", "канада"}:
        zone = "D"
    elif country in {"turkey", "türkiye", "турция", "түркия", "uae", "оаэ", "thailand", "таиланд", "egypt", "египет"}:
        zone = "C"
    elif country in {"uk", "united kingdom", "великобритания", "germany", "германия", "france", "франция", "italy", "италия", "spain", "испания"}:
        zone = "B"
    else:
        zone = "A"
    z = product["zones"][zone]
    start = _parse_date(slots["trip_start"])
    end = _parse_date(slots["trip_end"])
    days = max(1, (end - start).days + 1)
    travelers = _to_int(slots["travelers_count"])
    max_age = _to_int(slots["traveler_max_age"])
    if max_age > 75:
        raise ValueError("traveler_over_75")
    age_coef = 2.0 if max_age >= 65 else 1.0
    return round(z["rate_per_day_kzt"] * days * travelers * age_coef), zone, z["coverage"]


def execute_scenario(scenario_id: str, slots: dict[str, str], lang: str) -> tuple[str | None, dict[str, Any] | None]:
    """Deterministic read-only/simulated executor grounded in supplied JSON data."""
    scenario = scenario_map().get(scenario_id)
    if not scenario:
        return None, None

    handoff = scenario.get("handoff")
    if scenario_id == "SC37" or (handoff and "always" in str(handoff.get("when", "")).lower()):
        queue = (handoff or {}).get("queue", "operator_general")
        msg = _lang_text(
            lang,
            f"Передаю обращение оператору. Очередь: {queue}. Контекст разговора сохранён.",
            f"Өтінішті операторға жіберемін. Кезек: {queue}. Әңгіме контексті сақталды.",
        )
        return msg, {"queue": queue, "simulated": True, "reason": "scenario_handoff"}

    try:
        if scenario_id == "SC01":
            price = _ogpo_quote(slots)
            return _lang_text(
                lang,
                f"Предварительная стоимость ОГПО по указанным данным: {_money(price)}. Расчёт выполнен по синтетическим тарифам демо-набора.",
                f"Көрсетілген деректер бойынша ОГПО-ның алдын ала құны: {_money(price)}. Есеп демо-жинақтың синтетикалық тарифтерімен жасалды.",
            ), None

        if scenario_id == "SC06":
            price, zone, coverage = _travel_quote(slots)
            return _lang_text(
                lang,
                f"Предварительная стоимость туристической страховки: {_money(price)}. Зона {zone}, покрытие {coverage}. Для оформления потребуется отдельное подтверждение клиента.",
                f"Саяхат сақтандыруының алдын ала құны: {_money(price)}. {zone} аймағы, жабу сомасы {coverage}. Рәсімдеу үшін клиенттің бөлек растауы қажет.",
            ), None

        if scenario_id == "SC07":
            product = knowledge_base()["products"]["property"]
            sum_insured = str(_to_int(slots["sum_insured"]))
            price = product["price_per_year_kzt"].get(sum_insured)
            if price is None:
                return _lang_text(
                    lang,
                    "Для этой страховой суммы нужен индивидуальный расчёт оператора.",
                    "Бұл сақтандыру сомасы үшін оператордың жеке есебі қажет.",
                ), {"queue": "operator_general", "simulated": True, "reason": "nonstandard_property_sum"}
            if slots.get("property_type", "").lower() in {"house", "дом", "үй"}:
                price = round(price * product.get("house_coef", 1.0))
            return _lang_text(lang, f"Ориентировочная годовая стоимость: {_money(price)}.", f"Жылдық шамамен құны: {_money(price)}."), None

        if scenario_id == "SC08":
            product = knowledge_base()["products"]["accident"]
            price = product["price_per_year_kzt"].get(str(_to_int(slots["sum_insured"])))
            if price:
                return _lang_text(lang, f"Ориентировочная годовая стоимость: {_money(price)}.", f"Жылдық шамамен құны: {_money(price)}."), None

        if scenario_id == "SC17":
            claim = _find_claim(slots)
            if claim:
                return _lang_text(
                    lang,
                    f"Заявление {claim['claim_number']}: статус — {claim['status']}. Следующий шаг: {claim.get('next_step', 'уточняется')}.",
                    f"{claim['claim_number']} өтініші: мәртебесі — {claim['status']}. Келесі қадам: {claim.get('next_step', 'нақтылануда')}.",
                ), None
            return _lang_text(lang, "Заявление с таким номером в тестовых данных не найдено.", "Мұндай нөмірлі өтініш тест деректерінен табылмады."), None

        if scenario_id == "SC23":
            city = slots["city"].strip().lower()
            clinics = [x for x in knowledge_base().get("clinics", []) if x.get("city", "").lower() == city]
            if clinics:
                items = "; ".join(f"{x['name']} — {x['address']}" for x in clinics[:3])
                return _lang_text(lang, f"Партнёрские клиники: {items}.", f"Серіктес клиникалар: {items}."), None

        if scenario_id == "SC25":
            policy = _find_policy(slots)
            if policy:
                today = date.fromisoformat("2026-10-01")
                active = date.fromisoformat(policy["start_date"]) <= today <= date.fromisoformat(policy["end_date"])
                status = "действует" if active else "не действует"
                return _lang_text(
                    lang,
                    f"Полис {policy['policy_number']} {status}. Срок: {policy['start_date']} — {policy['end_date']}.",
                    f"{policy['policy_number']} полисі {'жарамды' if active else 'жарамсыз'}. Мерзімі: {policy['start_date']} — {policy['end_date']}.",
                ), None
            return _lang_text(lang, "Полис с таким номером в тестовых данных не найден.", "Мұндай нөмірлі полис тест деректерінен табылмады."), None

        if scenario_id == "SC31":
            p = knowledge_base()["payments"]
            methods = "; ".join(p["methods"])
            return _lang_text(lang, f"Доступные способы оплаты: {methods}. Наличные: {p['cash']}", f"Қолжетімді төлем тәсілдері: {methods}. Қолма-қол: {p['cash']}"), None

        if scenario_id == "SC33":
            city = slots["city"].strip().lower()
            office = next((x for x in knowledge_base().get("offices", []) if x.get("city", "").lower() == city), None)
            if office:
                return _lang_text(
                    lang,
                    f"Офис в {office['city']}: {office['address']}. Часы работы: {office['hours']}.",
                    f"{office['city']} кеңсесі: {office['address']}. Жұмыс уақыты: {office['hours']}.",
                ), None
            return _lang_text(lang, "В этом городе офис в тестовой базе не найден.", "Бұл қалада тест базасынан кеңсе табылмады."), None

        if scenario_id == "SC34":
            steps = knowledge_base()["app_help"]
            return _lang_text(
                lang,
                f"Для входа: {steps['login']} Если SMS не приходит: " + "; ".join(steps["sms_code_not_received"]),
                f"Кіру үшін: {steps['login']} SMS келмесе: " + "; ".join(steps["sms_code_not_received"]),
            ), None

        if scenario_id in {"SC09", "SC18", "SC22", "SC24", "SC32", "SC40"}:
            opening = scenario.get("responses", {}).get(lang, {}).get("opening") or scenario.get("responses", {}).get("ru", {}).get("opening")
            return opening, None

    except (ValueError, KeyError):
        if scenario_id == "SC06" and str(slots.get("traveler_max_age", "")).isdigit() and int(slots["traveler_max_age"]) > 75:
            return _lang_text(
                lang,
                "Для путешественника старше 75 лет нужен индивидуальный расчёт оператора.",
                "75 жастан асқан саяхатшы үшін оператордың жеке есебі қажет.",
            ), {"queue": "operator_general", "simulated": True, "reason": "traveler_over_75"}

    if scenario.get("requires_confirmation"):
        return _lang_text(
            lang,
            "Данные собраны. Необратимое действие не выполнено: перед ним требуется явное подтверждение клиента.",
            "Деректер жиналды. Қайтымсыз әрекет орындалмады: оған дейін клиенттің нақты растауы қажет.",
        ), None

    return None, None
