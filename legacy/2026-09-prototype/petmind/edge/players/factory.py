import os

from .base import MusicPlayer


def create_music_player(profile: str | None = None) -> MusicPlayer:
    selected = (profile or os.getenv("PETMIND_MUSIC_PLAYER", "simulated")).lower()
    if selected == "simulated":
        from .simulated import SimulatedMusicPlayer

        return SimulatedMusicPlayer()
    if selected == "youtube":
        from .youtube import YouTubeMusicPlayer

        return YouTubeMusicPlayer()
    raise ValueError(f"지원하지 않는 music player입니다: {selected}")
