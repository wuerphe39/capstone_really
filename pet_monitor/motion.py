"""규칙 기반 동작 분류.

카메라 추론(예: YOLO)이 프레임마다 내놓는 바운딩박스 중심 좌표(0~1 정규화)와 자세 라벨을
시간 윈도우로 모아 동작을 분류한다. 학습 데이터가 필요 없고, 이후 LSTM으로 교체할 수 있도록
`classify_window(observations) -> str` 인터페이스를 유지한다.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .context import MotionSummary

POSTURE_LOW = {"resting"}
POSTURE_HIGH = {"alert", "playing"}


@dataclass
class Observation:
    t: float          # 초
    cx: float         # 바운딩박스 중심 x (0~1)
    cy: float         # 바운딩박스 중심 y (0~1)
    behavior: str = ""  # 프레임 단위 자세/행동 라벨


@dataclass
class MotionConfig:
    window_s: float = 10.0
    stride_s: float = 5.0
    min_obs: int = 8
    smooth: int = 3
    still_extent: float = 0.05        # 이동 범위가 이보다 작으면 정지
    moving_extent: float = 0.20       # 이보다 크면 이동으로 간주
    spin_min_turns: float = 1.0       # 윈도우 내 최소 회전 수
    spin_max_extent: float = 0.35
    spin_min_aspect: float = 0.5      # 궤적 단축/장축 비 (직선 왕복과 구분)
    spin_consistency: float = 0.7     # 회전 방향 일관성
    pace_min_extent: float = 0.20
    pace_min_reversals: int = 2
    pace_max_aspect: float = 0.35
    posture_min_run: int = 2          # 이보다 짧은 자세 변화는 노이즈로 무시
    posture_min_flips: int = 3
    posture_max_extent: float = 0.15


def _smooth(a: np.ndarray, k: int) -> np.ndarray:
    if k <= 1 or len(a) < k:
        return a
    kernel = np.ones(k) / k
    pad = k // 2
    padded = np.pad(a, (pad, k - 1 - pad), mode="edge")
    return np.convolve(padded, kernel, mode="valid")


def _posture_flips(labels: list[str], min_run: int) -> int:
    """low/high 자세 사이를 오간 횟수 (짧은 구간은 무시)."""
    groups: list[tuple[str, int]] = []
    for lab in labels:
        g = "low" if lab in POSTURE_LOW else "high" if lab in POSTURE_HIGH else None
        if g is None:
            continue
        if groups and groups[-1][0] == g:
            groups[-1] = (g, groups[-1][1] + 1)
        else:
            groups.append((g, 1))
    groups = [g for g in groups if g[1] >= min_run]
    merged: list[str] = []
    for g, _ in groups:
        if not merged or merged[-1] != g:
            merged.append(g)
    return max(len(merged) - 1, 0)


def _reversals(proj: np.ndarray, min_swing: float) -> int:
    """진폭 min_swing 이상으로 방향이 바뀐 횟수."""
    count, direction, extreme = 0, 0, proj[0]
    for v in proj[1:]:
        if direction == 0:
            if v - extreme > min_swing:
                direction, extreme = 1, v
            elif extreme - v > min_swing:
                direction, extreme = -1, v
        elif direction == 1:
            if v > extreme:
                extreme = v
            elif extreme - v > min_swing:
                direction, extreme, count = -1, v, count + 1
        else:
            if v < extreme:
                extreme = v
            elif v - extreme > min_swing:
                direction, extreme, count = 1, v, count + 1
    return count


def classify_window(obs: list[Observation], cfg: MotionConfig | None = None) -> str:
    cfg = cfg or MotionConfig()
    if len(obs) < cfg.min_obs:
        return "unknown"
    xy = np.array([[o.cx, o.cy] for o in obs], dtype=float)
    xy = np.column_stack([_smooth(xy[:, 0], cfg.smooth), _smooth(xy[:, 1], cfg.smooth)])
    extent = float(max(np.ptp(xy[:, 0]), np.ptp(xy[:, 1])))
    flips = _posture_flips([o.behavior for o in obs], cfg.posture_min_run)

    center = xy.mean(axis=0)
    cov = np.cov((xy - center).T)
    eig = np.sort(np.linalg.eigvalsh(cov))[::-1]
    aspect = float(np.sqrt(max(eig[1], 0) / eig[0])) if eig[0] > 1e-12 else 0.0

    # 제자리 회전: 작은 원형 궤적을 일정한 방향으로 여러 바퀴
    if extent <= cfg.spin_max_extent and aspect >= cfg.spin_min_aspect and extent > cfg.still_extent:
        ang = np.unwrap(np.arctan2(xy[:, 1] - center[1], xy[:, 0] - center[0]))
        steps = np.diff(ang)
        total = float(np.abs(steps).sum())
        net = float(abs(steps.sum()))
        if total > 0 and net / (2 * np.pi) >= cfg.spin_min_turns and net / total >= cfg.spin_consistency:
            return "spinning"

    # 왕복 이동: 직선에 가까운 궤적을 오감
    if extent >= cfg.pace_min_extent and aspect <= cfg.pace_max_aspect:
        _, vecs = np.linalg.eigh(cov)
        proj = (xy - center) @ vecs[:, -1]
        if _reversals(proj, 0.25 * float(np.ptp(proj))) >= cfg.pace_min_reversals:
            return "pacing"

    if extent <= cfg.posture_max_extent and flips >= cfg.posture_min_flips:
        return "sit_stand_repeat"
    if extent < cfg.still_extent:
        return "still"
    if extent >= cfg.moving_extent:
        return "moving"
    return "still"


def summarize_motion(
    obs: list[Observation], window_s: float = 30.0, end_s: float | None = None,
    cfg: MotionConfig | None = None,
) -> MotionSummary:
    """최근 window_s 구간을 슬라이딩 윈도우로 분류해 라벨별 시간을 집계한다."""
    cfg = cfg or MotionConfig()
    if not obs:
        return MotionSummary(window_s, "unknown", {})
    end = obs[-1].t if end_s is None else end_s
    start = end - window_s
    seconds: dict[str, float] = {}
    t = start
    while t + cfg.window_s <= end + 1e-9:
        seg = [o for o in obs if t <= o.t < t + cfg.window_s]
        label = classify_window(seg, cfg)
        seconds[label] = seconds.get(label, 0.0) + cfg.stride_s
        t += cfg.stride_s
    if not seconds:
        seg = [o for o in obs if start <= o.t <= end]
        seconds[classify_window(seg, cfg)] = min(window_s, end - start)
    # 윈도우가 겹치므로 총합이 window_s가 되도록 정규화
    total = sum(seconds.values())
    seconds = {k: v * window_s / total for k, v in seconds.items()}
    dominant = max(seconds, key=seconds.get)
    return MotionSummary(window_s, dominant, seconds)
