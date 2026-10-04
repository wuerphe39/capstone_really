"""LLM/규칙 기반 판단기에 전달할 상태 요약 데이터 구조."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

MOTION_LABELS_KO = {
    "still": "정지",
    "moving": "이동",
    "spinning": "제자리 회전",
    "pacing": "왕복 이동",
    "sit_stand_repeat": "앉았다 일어남 반복",
    "unknown": "판단 불가",
}


@dataclass
class BarkSummary:
    window_s: float
    count: int
    rate_per_min: float
    peak_db: float | None  # dBFS, 짖음이 없으면 None
    mean_db: float | None
    total_bark_s: float
    level: str  # none | occasional | frequent


@dataclass
class MotionSummary:
    window_s: float
    dominant: str
    seconds_by_label: dict[str, float] = field(default_factory=dict)


@dataclass
class PetContext:
    timestamp: float
    window_s: float
    bark: BarkSummary
    motion: MotionSummary

    def to_dict(self) -> dict:
        return asdict(self)

    def to_text(self) -> str:
        b, m = self.bark, self.motion
        if b.count == 0:
            bark_text = f"최근 {b.window_s:.0f}초 동안 짖지 않았다."
        else:
            bark_text = (
                f"최근 {b.window_s:.0f}초 동안 {b.count}회 짖었다 "
                f"(분당 {b.rate_per_min:.1f}회, 최대 {b.peak_db:.0f} dBFS, 빈도: {b.level})."
            )
        parts = ", ".join(
            f"{MOTION_LABELS_KO.get(k, k)} {v:.0f}초"
            for k, v in sorted(m.seconds_by_label.items(), key=lambda kv: -kv[1])
            if v > 0
        )
        motion_text = (
            f"주된 동작은 '{MOTION_LABELS_KO.get(m.dominant, m.dominant)}'이다"
            + (f" ({parts})." if parts else ".")
        )
        return f"{bark_text} {motion_text}"
