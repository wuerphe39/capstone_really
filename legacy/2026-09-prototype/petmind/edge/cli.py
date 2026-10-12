"""Command-line entry point for isolated edge module tests."""

import argparse
import json
import os

from petmind.edge.agent import SensorAgent
from petmind.edge.sensors import create_sensor_suite
from petmind.edge.transport import HttpSensorPublisher


def test_sensor(profile: str, device_id: str | None) -> int:
    sensors = create_sensor_suite(profile, device_id)
    try:
        snapshot = sensors.read()
        print(json.dumps(snapshot.to_diagnostic_dict(), ensure_ascii=False, indent=2))
        return 0 if snapshot.valid else 2
    finally:
        sensors.close()


def run_agent(
    profile: str,
    device_id: str | None,
    api_base: str,
    interval: float,
    once: bool,
) -> int:
    sensors = create_sensor_suite(profile, device_id)
    publisher = HttpSensorPublisher(api_base)
    SensorAgent(sensors, publisher, interval).run(max_samples=1 if once else None)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="PetMind edge module runner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    test = subparsers.add_parser("test-sensor", help="센서를 한 번 읽고 진단값을 출력")
    test.add_argument("--profile", choices=["simulated", "raspberrypi"], default=None)
    test.add_argument("--device-id", default=None)

    run = subparsers.add_parser("run", help="센서 값을 백엔드로 지속 전송")
    run.add_argument("--profile", choices=["simulated", "raspberrypi"], default=None)
    run.add_argument("--device-id", default=None)
    run.add_argument("--api", default=os.getenv("PETMIND_API_BASE", "http://localhost:8000"))
    run.add_argument("--interval", type=float, default=3.0)
    run.add_argument("--once", action="store_true")

    args = parser.parse_args()
    profile = args.profile or os.getenv("PETMIND_EDGE_PROFILE", "simulated")
    if args.command == "test-sensor":
        return test_sensor(profile, args.device_id)
    return run_agent(profile, args.device_id, args.api, args.interval, args.once)


if __name__ == "__main__":
    raise SystemExit(main())
