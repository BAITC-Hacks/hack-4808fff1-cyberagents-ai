from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.data_store import dev_utterances
from app.router import LLMRouter
from app.schemas import DialogState


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=0, help="0 = all 104")
    p.add_argument("--out", default="predictions.json")
    args = p.parse_args()

    rows = dev_utterances()["utterances"]
    if args.limit:
        rows = rows[: args.limit]

    router = LLMRouter()
    predictions: dict[str, list[str]] = {}
    latencies: list[int] = []
    primary_ok = full_ok = 0
    multi_total = multi_recalled = 0

    for i, row in enumerate(rows, 1):
        decision, ms = router.route(row["text"], DialogState(session_id=row["id"]))
        pred = [x.scenario_id for x in decision.scenarios]
        expected = row["expected"]
        predictions[row["id"]] = pred
        latencies.append(ms)
        primary_ok += int(bool(pred) and pred[0] == expected[0])
        full_ok += int(pred == expected)
        if row["type"] == "multi_intent":
            multi_total += len(expected)
            multi_recalled += len(set(expected) & set(pred))
        print(f"[{i:03}/{len(rows)}] {row['id']} {row['lang']:<5} expected={expected} pred={pred} {ms}ms")

    Path(args.out).write_text(json.dumps(predictions, ensure_ascii=False, indent=2), encoding="utf-8")
    n = len(rows)
    print("\n=== METRICS ===")
    print(f"Primary accuracy: {primary_ok/n:.3%}")
    print(f"Full match:       {full_ok/n:.3%}")
    if multi_total:
        print(f"Multi recall:     {multi_recalled/multi_total:.3%}")
    if latencies:
        s=sorted(latencies)
        print(f"Router median:    {s[len(s)//2]} ms")
    print(f"Saved: {args.out}")


if __name__ == "__main__":
    main()
