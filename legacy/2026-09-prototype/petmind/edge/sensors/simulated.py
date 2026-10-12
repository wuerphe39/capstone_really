"""Repeatable sensor source for development without Raspberry Pi hardware."""

import math

from petmind.contracts import SensorSnapshot


class SimulatedSensorSuite:
    def __init__(self, device_id: str = "petmind-simulator"):
        self.device_id = device_id
        self.tick = 0

    @property
    def name(self) -> str:
        return "simulated"

    def read(self) -> SensorSnapshot:
        tick = self.tick
        self.tick += 1
        return SensorSnapshot(
            device_id=self.device_id,
            source=self.name,
            temperature=round(24 + math.sin(tick / 8), 1),
            humidity=round(50 + math.sin(tick / 10) * 3, 1),
            bark_detected=tick % 20 in {16, 17, 18},
            bark_count=3 if tick % 20 in {16, 17, 18} else 0,
            bark_volume=0.72 if tick % 20 in {16, 17, 18} else 0.0,
        )

    def close(self) -> None:
        return None
