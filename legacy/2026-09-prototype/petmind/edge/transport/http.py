"""HTTP adapter for publishing sensor snapshots to the backend."""

import requests

from petmind.contracts import SensorSnapshot


class HttpSensorPublisher:
    def __init__(self, api_base: str, timeout: float = 3.0):
        self.endpoint = f"{api_base.rstrip('/')}/sensors/"
        self.timeout = timeout
        self.session = requests.Session()

    def publish(self, snapshot: SensorSnapshot) -> dict:
        response = self.session.post(
            self.endpoint,
            json=snapshot.to_api_payload(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def close(self) -> None:
        self.session.close()
