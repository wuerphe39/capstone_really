"""Small orchestration layer that joins sensors to a transport adapter."""

import time

import requests

from petmind.edge.sensors.base import SensorSuite
from petmind.edge.transport import HttpSensorPublisher


class SensorAgent:
    def __init__(
        self,
        sensors: SensorSuite,
        publisher: HttpSensorPublisher,
        interval: float = 3.0,
    ):
        self.sensors = sensors
        self.publisher = publisher
        self.interval = max(2.5, interval)

    def run(self, max_samples: int | None = None) -> None:
        samples = 0
        try:
            while max_samples is None or samples < max_samples:
                snapshot = self.sensors.read()
                try:
                    self.publisher.publish(snapshot)
                    print(f"[sensor:{self.sensors.name}] {snapshot.to_diagnostic_dict()}")
                except requests.RequestException as exc:
                    print(f"[sensor:{self.sensors.name}] 전송 실패, 다음 주기에 재시도합니다: {exc}")
                samples += 1
                if max_samples is None or samples < max_samples:
                    time.sleep(self.interval)
        except KeyboardInterrupt:
            pass
        finally:
            self.sensors.close()
            self.publisher.close()
