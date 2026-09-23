from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.executor import execute_scenario


def main() -> None:
    cases = [
        (
            "SC01",
            {
                "region": "almaty",
                "vehicle_type": "car",
                "drivers_iin": "850314300121",
            },
            "30 400",
        ),
        (
            "SC06",
            {
                "trip_country": "Турция",
                "trip_start": "2026-10-10",
                "trip_end": "2026-10-16",
                "travelers_count": "2",
                "traveler_max_age": "42",
            },
            "15 400",
        ),
        ("SC17", {"claim_number": "CL-500330"}, "CL-500330"),
        ("SC33", {"city": "Astana"}, "Mangilik El"),
    ]

    for scenario_id, slots, expected in cases:
        reply, _ = execute_scenario(scenario_id, slots, "ru")
        assert reply and expected in reply, (scenario_id, reply)
        print(f"PASS {scenario_id}: {reply}")

    print("Smoke checks passed.")


if __name__ == "__main__":
    main()
