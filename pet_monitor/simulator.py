"""하드웨어 없이 짖음 오디오와 동작 궤적을 합성하는 시뮬레이터."""
from __future__ import annotations

import numpy as np

from .motion import Observation

SAMPLE_RATE = 16000


def make_audio(duration_s: float, bark_times: list[float], noise_amp: float = 0.003,
               bark_amp: float = 0.2, bark_len_s: float = 0.2, seed: int = 0) -> np.ndarray:
    """배경 잡음 위에 지정한 시각마다 짖음(감쇠하는 배음 + 잡음)을 합성한다."""
    rng = np.random.default_rng(seed)
    n = int(duration_s * SAMPLE_RATE)
    x = rng.normal(0, noise_amp, n).astype(np.float32)
    m = int(bark_len_s * SAMPLE_RATE)
    t = np.arange(m) / SAMPLE_RATE
    env = np.exp(-t / (bark_len_s / 3))
    tone = np.sin(2 * np.pi * 600 * t) + 0.5 * np.sin(2 * np.pi * 1200 * t)
    burst = (bark_amp * env * (0.8 * tone / 1.5 + 0.2 * rng.normal(0, 1, m))).astype(np.float32)
    for bt in bark_times:
        i = int(bt * SAMPLE_RATE)
        if i + m <= n:
            x[i:i + m] += burst
    return x


def make_trajectory(kind: str, duration_s: float, fps: float = 5.0, t0: float = 0.0,
                    seed: int = 0) -> list[Observation]:
    """동작 종류별 바운딩박스 중심 궤적(정규화 좌표)과 자세 라벨을 합성한다."""
    rng = np.random.default_rng(seed)
    ts = np.arange(0, duration_s, 1.0 / fps)
    jitter = lambda: rng.normal(0, 0.003, 2)
    out: list[Observation] = []
    for t in ts:
        behavior = "alert"
        if kind == "still":
            cx, cy, behavior = 0.5, 0.5, "resting"
        elif kind == "moving":  # 한 방향으로 걸어감
            cx, cy = 0.1 + 0.8 * (t / duration_s), 0.5 + 0.05 * np.sin(t)
        elif kind == "spinning":  # 반지름 0.08, 2초에 1바퀴
            a = 2 * np.pi * t / 2.0
            cx, cy, behavior = 0.5 + 0.08 * np.cos(a), 0.5 + 0.08 * np.sin(a), "playing"
        elif kind == "pacing":  # 가로로 0.3 진폭, 4초 주기 왕복
            cx, cy = 0.5 + 0.3 * np.sin(2 * np.pi * t / 4.0), 0.5
        elif kind == "sit_stand_repeat":  # 제자리에서 1.5초마다 자세 전환
            cx, cy = 0.5, 0.5
            behavior = "resting" if int(t / 1.5) % 2 == 0 else "alert"
        else:
            raise ValueError(f"unknown kind: {kind}")
        dx, dy = jitter()
        out.append(Observation(t=t0 + float(t), cx=float(cx + dx), cy=float(cy + dy), behavior=behavior))
    return out


SCENARIOS = {
    # 이름: (30초 오디오의 짖음 시각, 30초 동안의 동작 구간 [(종류, 길이)])
    "calm": ([], [("still", 30)]),
    "anxious": ([2.0, 3.5, 5.0, 6.2, 9.0, 10.5, 14.0, 20.0], [("spinning", 20), ("pacing", 10)]),
    "bored_pacing": ([12.0, 25.0], [("still", 10), ("pacing", 20)]),
}


def make_scenario(name: str, seed: int = 0) -> tuple[np.ndarray, list[Observation]]:
    bark_times, segments = SCENARIOS[name]
    audio = make_audio(30.0, bark_times, seed=seed)
    obs: list[Observation] = []
    t = 0.0
    for i, (kind, length) in enumerate(segments):
        obs += make_trajectory(kind, length, t0=t, seed=seed + i)
        t += length
    return audio, obs
