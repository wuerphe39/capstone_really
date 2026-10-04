"""짖음·동작 요약을 하나의 PetContext로 묶는다."""
from __future__ import annotations

from .bark import BarkDetector
from .context import PetContext
from .motion import MotionConfig, Observation, summarize_motion


def build_context(detector: BarkDetector, observations: list[Observation],
                  window_s: float = 30.0, motion_cfg: MotionConfig | None = None) -> PetContext:
    return PetContext(
        timestamp=detector.now_s,
        window_s=window_s,
        bark=detector.summarize(window_s),
        motion=summarize_motion(observations, window_s, cfg=motion_cfg),
    )
