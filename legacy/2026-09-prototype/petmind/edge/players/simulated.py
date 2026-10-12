class SimulatedMusicPlayer:
    def play(self, style: str) -> str:
        message = f"음악 재생 시뮬레이션: {style}"
        print(f"[music] {message}")
        return message
