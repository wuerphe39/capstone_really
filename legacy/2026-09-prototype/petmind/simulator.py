"""Generate repeatable PetMind presentation scenarios against a running API."""
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

import requests


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


API_BASE = os.getenv("PETMIND_API_BASE", "http://localhost:8000")


SCENARIOS = {
    "normal": {
        "sensor": {"temperature": 24, "humidity": 48, "feed_remaining_g": 350, "bark_detected": False, "bark_count": 0, "bark_volume": 0},
        "context": {"observed_behavior": "resting", "behavior_confidence": 0.94, "behavior_duration_seconds": 25, "temperature": 24, "humidity": 48, "feed_remaining_g": 350},
    },
    "anxious": {
        "sensor": {"temperature": 25, "humidity": 55, "feed_remaining_g": 300, "bark_detected": True, "bark_count": 5, "bark_volume": 0.82},
        "context": {"observed_behavior": "anxious", "behavior_confidence": 0.91, "behavior_duration_seconds": 18, "bark_detected": True, "bark_count": 5, "bark_volume": 0.82, "temperature": 25, "humidity": 55, "feed_remaining_g": 300},
    },
    "feeding": {
        "context": {
            "observed_behavior": "resting",
            "behavior_confidence": 0.82,
            "behavior_duration_seconds": 20,
            "bark_detected": False,
            "bark_count": 0,
            "bark_volume": 0,
            "temperature": 24,
            "humidity": 50,
            "feed_remaining_g": 350,
            "last_feeding_at": (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat(),
            "last_feeding_amount_g": 50,
            "feeding_due": True,
        }
    },
}


def post(path: str, payload: dict):
    response = requests.post(f"{API_BASE}{path}", json=payload, timeout=5)
    response.raise_for_status()
    return response.json()


def run(name: str, approve: bool = False):
    scenario = SCENARIOS[name]
    if "sensor" in scenario:
        post("/sensors/", scenario["sensor"])
    result = post("/care/evaluate", {"context": scenario["context"]})
    print(f"[{name}] {result['summary']}")
    print(f"  provider={result['provider']} severity={result['severity']}")
    for reason in result["reasons"]:
        print(f"  reason: {reason}")
    print(f"  actions={result['recommended_actions']} id={result['id']}")
    if approve:
        for action_type in result["recommended_actions"]:
            action = post(
                f"/care/{result['id']}/approve",
                {"action_type": action_type},
            )
            print(f"  approved={action_type} status={action['status']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", choices=[*SCENARIOS, "all"], default="all", nargs="?")
    parser.add_argument(
        "--approve",
        action="store_true",
        help="approve every recommended action (use only in simulation or a safe test rig)",
    )
    args = parser.parse_args()
    names = SCENARIOS if args.scenario == "all" else [args.scenario]
    for scenario_name in names:
        run(scenario_name, approve=args.approve)
