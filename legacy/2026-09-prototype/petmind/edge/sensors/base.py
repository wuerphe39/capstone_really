"""Sensor interfaces. Implementations must not perform network operations."""

from typing import Protocol

from petmind.contracts import SensorSnapshot


class SensorSuite(Protocol):
    @property
    def name(self) -> str: ...

    def read(self) -> SensorSnapshot: ...

    def close(self) -> None: ...
