"""Transport-neutral sensor data produced by a PetMind edge device."""

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class SensorSnapshot:
    device_id: str
    source: str
    captured_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    temperature: float | None = None
    humidity: float | None = None
    bark_detected: bool = False
    bark_count: int = 0
    bark_volume: float = 0.0
    valid: bool = True
    errors: tuple[str, ...] = ()

    def to_api_payload(self) -> dict:
        """Return the fields accepted by the current backend sensor endpoint."""
        return {
            "temperature": self.temperature,
            "humidity": self.humidity,
            "bark_detected": self.bark_detected,
            "bark_count": self.bark_count,
            "bark_volume": self.bark_volume,
        }

    def to_diagnostic_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "source": self.source,
            "captured_at": self.captured_at.isoformat(),
            **self.to_api_payload(),
            "valid": self.valid,
            "errors": list(self.errors),
        }
