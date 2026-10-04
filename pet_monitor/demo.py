"""시나리오를 합성해 PetContext 출력까지 확인하는 데모.

    python -m pet_monitor.demo            # 전체 시나리오
    python -m pet_monitor.demo anxious    # 하나만
"""
import json
import sys

from .bark import BarkDetector
from .build import build_context
from .simulator import SCENARIOS, SAMPLE_RATE, make_scenario


def run(name: str) -> None:
    audio, obs = make_scenario(name)
    det = BarkDetector()
    chunk = SAMPLE_RATE // 2  # 0.5초 단위 스트리밍 입력
    for i in range(0, len(audio), chunk):
        det.feed(audio[i:i + chunk])
    ctx = build_context(det, obs)
    print(f"=== {name} ===")
    print(ctx.to_text())
    print(json.dumps(ctx.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    for n in (sys.argv[1:] or list(SCENARIOS)):
        run(n)
