"""Continuously send camera inference signals to the PetMind backend."""

import argparse
import time
from pathlib import Path

import cv2
import requests

from pipeline import PetMindPipeline


def source_value(value: str):
    return int(value) if value.isdigit() else value


def run(api_base: str, source: str, interval: float, show: bool) -> None:
    endpoint = f"{api_base.rstrip('/')}/analysis/"
    pipeline = PetMindPipeline()
    capture = cv2.VideoCapture(source_value(source))
    if not capture.isOpened():
        raise RuntimeError(f"카메라 또는 영상 파일을 열 수 없습니다: {source}")

    session = requests.Session()
    last_sent = 0.0
    try:
        while capture.isOpened():
            ok, frame = capture.read()
            if not ok:
                break
            predictions = pipeline.predict(frame)
            if predictions and time.monotonic() - last_sent >= interval:
                strongest = max(predictions, key=lambda item: item["behavior_conf"])
                payload = {
                    "behavior": strongest["behavior"],
                    "behavior_conf": strongest["behavior_conf"],
                    "emotion": strongest["emotion"],
                    "emotion_conf": strongest["emotion_conf"],
                }
                try:
                    response = session.post(endpoint, json=payload, timeout=3)
                    response.raise_for_status()
                    last_sent = time.monotonic()
                except requests.RequestException as exc:
                    print(f"[AI] 백엔드 전송 실패, 다음 주기에 재시도합니다: {exc}")

            if show:
                cv2.imshow("PetMind visual signal", pipeline.draw(frame, predictions))
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    finally:
        capture.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--source", default="0", help="camera index or video path")
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()
    if not args.source.isdigit() and not Path(args.source).is_file():
        raise SystemExit(f"영상 파일이 없습니다: {args.source}")
    run(args.api, args.source, max(0.2, args.interval), args.show)
