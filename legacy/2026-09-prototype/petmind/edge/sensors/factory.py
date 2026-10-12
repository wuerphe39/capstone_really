"""Construct sensor implementations from an explicit runtime profile."""

import os

from .base import SensorSuite


def create_sensor_suite(
    profile: str | None = None,
    device_id: str | None = None,
) -> SensorSuite:
    selected = (profile or os.getenv("PETMIND_EDGE_PROFILE", "simulated")).lower()
    identity = device_id or os.getenv("PETMIND_DEVICE_ID", f"petmind-{selected}")
    if selected == "simulated":
        from .simulated import SimulatedSensorSuite

        return SimulatedSensorSuite(identity)
    if selected == "raspberrypi":
        from .raspberrypi import RaspberryPiSensorSuite

        return RaspberryPiSensorSuite(identity)
    raise ValueError(f"지원하지 않는 edge profile입니다: {selected}")
