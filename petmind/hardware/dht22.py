import time
import board
import adafruit_dht

DHT_PIN = board.D4
READ_INTERVAL = 2.5  # DHT22 최소 샘플링 간격(초)


class DHT22Sensor:
    def __init__(self, pin=DHT_PIN):
        self.sensor = adafruit_dht.DHT22(pin)
        self._last_read = 0.0
        self._last_temp = None
        self._last_humidity = None

    def read(self) -> dict:
        now = time.time()
        if now - self._last_read < READ_INTERVAL:
            return {"temperature": self._last_temp, "humidity": self._last_humidity}

        try:
            self._last_temp = self.sensor.temperature
            self._last_humidity = self.sensor.humidity
            self._last_read = now
        except RuntimeError:
            pass  # 간헐적 읽기 오류 — 이전 값 유지

        return {"temperature": self._last_temp, "humidity": self._last_humidity}

    def cleanup(self):
        self.sensor.exit()
