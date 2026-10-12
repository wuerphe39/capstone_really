"""Backward-compatible wrapper around the modular PetMind edge sensor agent."""

import argparse

from petmind.edge.agent import SensorAgent
from petmind.edge.sensors import create_sensor_suite
from petmind.edge.sensors.simulated import SimulatedSensorSuite
from petmind.edge.transport import HttpSensorPublisher


def simulated_snapshot(tick: int) -> dict:
    suite = SimulatedSensorSuite()
    suite.tick = tick
    return suite.read().to_api_payload()


def run(api_base: str, interval: float, simulate: bool) -> None:
    profile = "simulated" if simulate else "raspberrypi"
    SensorAgent(
        create_sensor_suite(profile),
        HttpSensorPublisher(api_base),
        interval,
    ).run()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--interval", type=float, default=3.0)
    parser.add_argument("--simulate", action="store_true")
    args = parser.parse_args()
    run(args.api, args.interval, args.simulate)
