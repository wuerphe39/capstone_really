from typing import Protocol


class MusicPlayer(Protocol):
    def play(self, style: str) -> str: ...
