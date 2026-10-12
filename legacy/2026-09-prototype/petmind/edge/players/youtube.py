"""Allow-listed YouTube audio player for a Raspberry Pi with mpv installed."""

import os
import re
import shutil
import subprocess


VIDEO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")
STYLE_ENV = {
    "calm_piano": "PETMIND_YOUTUBE_CALM_PIANO_ID",
    "nature_sounds": "PETMIND_YOUTUBE_NATURE_SOUNDS_ID",
    "white_noise": "PETMIND_YOUTUBE_WHITE_NOISE_ID",
}


class YouTubeMusicPlayer:
    def __init__(self, executable: str | None = None):
        self.executable = executable or os.getenv("PETMIND_MUSIC_COMMAND", "mpv")

    def play(self, style: str) -> str:
        env_name = STYLE_ENV.get(style)
        if not env_name:
            raise ValueError(f"허용되지 않은 음악 유형입니다: {style}")
        video_id = os.getenv(env_name, "").strip()
        if not VIDEO_ID_PATTERN.fullmatch(video_id):
            raise RuntimeError(f"{env_name}에 유효한 YouTube 영상 ID를 설정하세요.")
        executable = shutil.which(self.executable)
        if not executable:
            raise RuntimeError(f"YouTube 재생 명령을 찾을 수 없습니다: {self.executable}")
        url = f"https://www.youtube.com/watch?v={video_id}"
        subprocess.Popen(
            [executable, "--no-video", "--force-window=no", url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return f"YouTube 음악 재생 시작: {style}"
