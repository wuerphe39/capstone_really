"""에너지 기반 짖음 감지.

마이크 샘플(모노 float, -1..1)을 연속으로 받아 50ms 프레임의 RMS(dBFS)를 계산하고,
적응형 잡음 바닥 + 이력(hysteresis) 임계값으로 짖음 이벤트를 만든다.
감정 분류는 하지 않고 횟수·음량·지속시간만 산출한다.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .context import BarkSummary


@dataclass
class BarkEvent:
    start_s: float
    duration_s: float
    peak_db: float
    mean_db: float


@dataclass
class BarkConfig:
    sample_rate: int = 16000
    frame_ms: int = 50
    margin_db: float = 12.0       # 잡음 바닥보다 이만큼 커야 시작
    release_db: float = 3.0       # 시작 임계값보다 이만큼 내려가야 종료 후보
    abs_min_db: float = -45.0     # 이보다 작은 소리는 무시
    release_frames: int = 2       # 종료 후보가 이 프레임 수 이어지면 이벤트 종료
    min_frames: int = 2           # 이보다 짧은 소리는 클릭 잡음으로 간주
    max_event_s: float = 1.5      # 이보다 긴 소리는 짖음이 아닌 지속 소음으로 간주
    noise_alpha: float = 0.05     # 잡음 바닥 EMA 계수
    occasional_max: int = 3       # 윈도우당 이 횟수 이하면 occasional


class BarkDetector:
    def __init__(self, config: BarkConfig | None = None):
        self.cfg = config or BarkConfig()
        self.frame_len = self.cfg.sample_rate * self.cfg.frame_ms // 1000
        self.frame_s = self.cfg.frame_ms / 1000
        self._buf = np.zeros(0, dtype=np.float32)
        self._frame_idx = 0
        self._noise_db: float | None = None
        self._active = False
        self._start_idx = 0
        self._levels: list[float] = []
        self._quiet_run = 0
        self.events: list[BarkEvent] = []

    @property
    def noise_floor_db(self) -> float | None:
        return self._noise_db

    @property
    def now_s(self) -> float:
        return self._frame_idx * self.frame_s

    def calibrate(self, samples: np.ndarray) -> None:
        """조용한 구간으로 잡음 바닥을 미리 설정한다(선택)."""
        levels = [self._rms_db(f) for f in self._frames(np.asarray(samples, np.float32))]
        if levels:
            self._noise_db = float(np.median(levels))

    def feed(self, samples: np.ndarray) -> list[BarkEvent]:
        """샘플을 추가하고, 이번 호출에서 완료된 이벤트를 반환한다."""
        self._buf = np.concatenate([self._buf, np.asarray(samples, np.float32)])
        n = len(self._buf) // self.frame_len
        new_events: list[BarkEvent] = []
        for i in range(n):
            frame = self._buf[i * self.frame_len:(i + 1) * self.frame_len]
            ev = self._step(self._rms_db(frame))
            if ev:
                new_events.append(ev)
        self._buf = self._buf[n * self.frame_len:]
        return new_events

    def summarize(self, window_s: float = 30.0, end_s: float | None = None) -> BarkSummary:
        end = self.now_s if end_s is None else end_s
        start = end - window_s
        evs = [e for e in self.events if start <= e.start_s < end]
        if not evs:
            return BarkSummary(window_s, 0, 0.0, None, None, 0.0, "none")
        count = len(evs)
        level = "occasional" if count <= self.cfg.occasional_max else "frequent"
        return BarkSummary(
            window_s=window_s,
            count=count,
            rate_per_min=count * 60.0 / window_s,
            peak_db=max(e.peak_db for e in evs),
            mean_db=float(np.mean([e.mean_db for e in evs])),
            total_bark_s=float(sum(e.duration_s for e in evs)),
            level=level,
        )

    # --- 내부 ---
    def _frames(self, x: np.ndarray):
        for i in range(len(x) // self.frame_len):
            yield x[i * self.frame_len:(i + 1) * self.frame_len]

    @staticmethod
    def _rms_db(frame: np.ndarray) -> float:
        rms = float(np.sqrt(np.mean(np.square(frame, dtype=np.float64))))
        return 20.0 * np.log10(rms + 1e-9)

    def _threshold(self) -> float:
        base = self._noise_db if self._noise_db is not None else self.cfg.abs_min_db
        return max(base + self.cfg.margin_db, self.cfg.abs_min_db)

    def _step(self, level_db: float) -> BarkEvent | None:
        cfg = self.cfg
        if self._noise_db is None:
            self._noise_db = level_db
        thr = self._threshold()
        event = None

        if not self._active:
            if level_db > thr:
                self._active = True
                self._start_idx = self._frame_idx
                self._levels = [level_db]
                self._quiet_run = 0
            else:
                # 소리가 없는 프레임으로만 잡음 바닥을 갱신
                self._noise_db += cfg.noise_alpha * (level_db - self._noise_db)
        else:
            self._levels.append(level_db)
            if level_db < thr - cfg.release_db:
                self._quiet_run += 1
            else:
                self._quiet_run = 0
            too_long = len(self._levels) * self.frame_s > cfg.max_event_s
            if self._quiet_run >= cfg.release_frames or too_long:
                active_levels = self._levels[: len(self._levels) - self._quiet_run] or self._levels
                dur = len(active_levels) * self.frame_s
                if not too_long and len(active_levels) >= cfg.min_frames:
                    event = BarkEvent(
                        start_s=self._start_idx * self.frame_s,
                        duration_s=dur,
                        peak_db=max(active_levels),
                        mean_db=float(np.mean(active_levels)),
                    )
                    self.events.append(event)
                self._active = False
                self._levels = []
                self._quiet_run = 0
        self._frame_idx += 1
        return event
