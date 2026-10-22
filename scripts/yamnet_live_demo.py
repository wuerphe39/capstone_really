"""YAMNet 짖음 후보 감지 데모 (중간발표 시연용, 운영 API와 연결되지 않음).

공개 음원 파일을 이어 붙여 실시간 속도로 흘려보내며, 0.5초마다 최근 1.5초 구간의 YAMNet
`Bark` 점수를 계산해 짖음 후보 구간의 시작·종료를 출력한다. 마이크 입력은
이 스크립트에서 검증하지 않았다. 점수·기준은 정확도가 아니다.

    python -m scripts.yamnet_live_demo --input a.wav b.wav --realtime --play
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

SAMPLE_RATE = 16000
WINDOW_S = 1.5
STEP_S = 0.5
DEFAULT_THRESHOLD = 0.05  # docs/47에서 사용한 YAMNet Bark 기준


@dataclass
class TrackerEvent:
    kind: str  # "start" | "end"
    t: float
    score: float = 0.0
    duration: float = 0.0
    peak: float = 0.0
    start: float = 0.0


class BarkEventTracker:
    """점수 시퀀스를 짖음 후보 구간으로 묶는다. 기준 미만이 hold번 이어지면 종료한다."""

    def __init__(self, threshold: float = DEFAULT_THRESHOLD, hold: int = 2):
        if not 0 < threshold <= 1 or hold < 1:
            raise ValueError("threshold는 (0, 1], hold는 1 이상이어야 한다")
        self.threshold, self.hold = threshold, hold
        self._start: float | None = None
        self._peak = 0.0
        self._quiet = 0
        self._last_hot = 0.0

    @property
    def active(self) -> bool:
        return self._start is not None

    def feed(self, t: float, score: float) -> list[TrackerEvent]:
        out: list[TrackerEvent] = []
        if score >= self.threshold:
            if self._start is None:
                self._start, self._peak = t, score
                out.append(TrackerEvent("start", t, score))
            self._peak = max(self._peak, score)
            self._quiet, self._last_hot = 0, t
        elif self._start is not None:
            self._quiet += 1
            if self._quiet >= self.hold:
                out.append(self._close())
        return out

    def finish(self) -> list[TrackerEvent]:
        return [self._close()] if self._start is not None else []

    def _close(self) -> TrackerEvent:
        ev = TrackerEvent("end", self._last_hot, duration=self._last_hot - self._start + STEP_S, peak=self._peak, start=self._start)
        self._start, self._peak, self._quiet = None, 0.0, 0
        return ev


def mmss(t: float) -> str:
    return f"{int(t) // 60:02d}:{t % 60:04.1f}"


def bar(score: float, width: int = 20) -> str:
    n = round(min(max(score, 0.0), 1.0) * width)
    return "#" * n + "." * (width - n)


def load_stream(paths: list[str], gap_s: float = 1.0):
    import numpy as np
    import soundfile as sf
    from scipy.signal import resample_poly

    parts = []
    for p in paths:
        x, sr = sf.read(p, dtype="float32")
        if x.ndim > 1:
            x = x.mean(axis=1)
        if sr != SAMPLE_RATE:
            x = resample_poly(x, SAMPLE_RATE, sr).astype("float32")
        parts += [x, np.zeros(int(gap_s * SAMPLE_RATE), "float32")]
    return np.concatenate(parts)


def load_model():
    import csv

    import tensorflow_hub as hub

    model = hub.load("https://tfhub.dev/google/yamnet/1")
    names = [r["display_name"] for r in csv.DictReader(open(model.class_map_path().numpy().decode(), encoding="utf-8"))]
    return model, names.index("Bark")


def play_async(stream, tmp: Path) -> bool:
    try:
        import winsound

        import soundfile as sf

        sf.write(tmp, stream, SAMPLE_RATE)
        winsound.PlaySound(str(tmp), winsound.SND_FILENAME | winsound.SND_ASYNC)
        return True
    except Exception as exc:  # Windows 외 환경 등
        print(f"[경고] 소리 재생을 건너뜁니다: {exc}")
        return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", nargs="+", required=True, help="WAV 파일(순서대로 이어 붙임)")
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    ap.add_argument("--realtime", action="store_true", help="실제 재생 속도로 출력")
    ap.add_argument("--play", action="store_true", help="Windows에서 입력 소리를 함께 재생")
    ap.add_argument("--names", nargs="*", help="--input과 같은 순서의 표시 이름(선택)")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    stream = load_stream(args.input)
    print(f"[준비] 입력 {len(args.input)}개 · 총 {len(stream) / SAMPLE_RATE:.1f}초 · YAMNet 로딩 중...")
    model, bark_idx = load_model()
    print(f"[준비] 완료 · 창 {WINDOW_S}초 / 간격 {STEP_S}초 / 감지 기준 Bark ≥ {args.threshold}")
    print("-" * 64)

    win, step = int(WINDOW_S * SAMPLE_RATE), int(STEP_S * SAMPLE_RATE)
    tracker = BarkEventTracker(args.threshold)
    n_events = 0
    started = time.monotonic()
    if args.play:
        play_async(stream, Path("_yamnet_demo_play.wav"))
    pos = win
    while pos <= len(stream):
        t = pos / SAMPLE_RATE
        if args.realtime:
            delay = started + t - time.monotonic()
            if delay > 0:
                time.sleep(delay)
        score = float(model(stream[pos - win:pos])[0].numpy()[:, bark_idx].max())
        tag = "  << 짖음 후보" if score >= args.threshold else ""
        print(f"{mmss(t)}  Bark {bar(score)} {score:5.3f}{tag}", flush=True)
        for ev in tracker.feed(t, score):
            if ev.kind == "start":
                n_events += 1
                print(f"{mmss(ev.t)}  [감지 시작] 짖음 후보 #{n_events} (점수 {ev.score:.3f})", flush=True)
            else:
                print(f"{mmss(t)}  [감지 종료] 구간 {mmss(ev.start)}~{mmss(ev.t + STEP_S)} (약 {ev.duration:.1f}초) · 최고 {ev.peak:.3f}", flush=True)
        pos += step
    for ev in tracker.finish():
        print(f"{mmss(len(stream) / SAMPLE_RATE)}  [감지 종료] 구간 {mmss(ev.start)}~{mmss(ev.t + STEP_S)} (약 {ev.duration:.1f}초) · 최고 {ev.peak:.3f}", flush=True)
    print("-" * 64)
    print(f"[요약] 짖음 후보 구간 {n_events}개 · 설명용 데모이며 정확도를 뜻하지 않음")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
