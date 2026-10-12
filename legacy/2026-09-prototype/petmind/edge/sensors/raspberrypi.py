"""Raspberry Pi sensor adapters with hardware imports delayed until startup."""

from petmind.contracts import SensorSnapshot


class RaspberryPiSensorSuite:
    def __init__(self, device_id: str = "petmind-rpi"):
        try:
            from petmind.hardware.dht22 import DHT22Sensor
        except (ImportError, RuntimeError) as exc:
            raise RuntimeError(
                "Raspberry Pi 센서 라이브러리를 불러올 수 없습니다. "
                "PC에서는 --profile simulated를 사용하세요."
            ) from exc
        self.device_id = device_id
        self.environment = DHT22Sensor()

    @property
    def name(self) -> str:
        return "raspberrypi"

    def read(self) -> SensorSnapshot:
        errors: list[str] = []
        try:
            environment = self.environment.read()
        except Exception as exc:
            environment = {"temperature": None, "humidity": None}
            errors.append(f"dht22: {exc}")
        temperature = environment.get("temperature")
        humidity = environment.get("humidity")
        if temperature is None or humidity is None:
            errors.append("dht22: 유효한 측정값이 없습니다")
        return SensorSnapshot(
            device_id=self.device_id,
            source=self.name,
            temperature=temperature,
            humidity=humidity,
            valid=not errors,
            errors=tuple(errors),
        )

    def close(self) -> None:
        self.environment.cleanup()
