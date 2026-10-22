"""시연용 기록을 채운다: 공개 음원(ESC-50)으로 외출 2개를 만들어 로컬 API에 올린다.

    python -m scripts.prepare_demo_audio          # 공개 음원 4개 내려받기(최초 1회)
    python -m scripts.seed_demo_records           # 외출 2개 + 시연 담당자 의견(실시간으로 약 40초 걸린다)

- 모든 기록에 공개 자료 출처(demo_source)를 붙여 개인 기록과 구분한다. 실제 반려견 기록이 아니다.
- 파일 이름 끝의 ESC-50 분류 번호로 의견을 정한다: 0(개) → 개 소리, 그 밖 → 기타.
- 이미 같은 반려견의 외출이 있으면 중복 생성을 막기 위해 중단한다(--force로 무시).
"""
from __future__ import annotations

import argparse
import re
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ESC50_DOG, ESC50_RAIN = "0", "10"
CLIP_SPACING_S = 6  # 5초 클립이 서로 겹치지 않도록 간격을 둔다
CLIP_DURATION_S = 5.0  # ESC-50 클립 길이


def classify(path: Path) -> tuple[str, str]:
    """(의견 라벨, 설명). 파일 이름 끝의 ESC-50 분류 번호로 판단한다."""
    m = re.search(r"-(\d+)\.wav$", path.name)
    cls = m.group(1) if m else ""
    if cls == ESC50_DOG:
        return "pet_vocalization", "공개 음원: 개 짖음(시연 담당자 확인)"
    if cls == ESC50_RAIN:
        return "other", "공개 음원: 빗소리(개 소리 아님)"
    return "uncertain", "공개 음원: 분류 미확인"


def split_outings(files: list[Path]) -> list[tuple[str, list[Path]]]:
    quiet = [f for f in files if classify(f)[0] != "pet_vocalization"]
    barking = [f for f in files if classify(f)[0] == "pet_vocalization"]
    plan = []
    if quiet:
        plan.append(("조용했던 외출 (공개 음원 시연)", quiet))
    if barking:
        plan.append(("짖음이 있던 외출 (공개 음원 시연)", barking))
    return plan


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://127.0.0.1:8010")
    ap.add_argument("--pet-id", default="demo-dog", help="화면의 기본 반려견 ID와 같다")
    ap.add_argument("--audio-dir", type=Path, default=Path("artifacts/datasets/esc50_demo/audio"))
    ap.add_argument("--force", action="store_true", help="이미 외출이 있어도 추가한다")
    args = ap.parse_args(argv)

    files = sorted(args.audio_dir.glob("*.wav"))
    if not files:
        print(f"음원이 없습니다: {args.audio_dir}  (먼저 python -m scripts.prepare_demo_audio)", file=sys.stderr)
        return 2
    base = args.base.rstrip("/")
    http = requests.Session()

    def call(method: str, route: str, **kw):
        r = http.request(method, base + route, timeout=120, **kw)
        if not r.ok:
            raise SystemExit(f"{method} {route} -> {r.status_code}: {r.text[:300]}")
        return r.json()

    existing = call("GET", "/outings", params={"pet_id": args.pet_id})
    existing = existing if isinstance(existing, list) else existing.get("items", existing.get("outings", []))
    if existing and not args.force:
        print(f"{args.pet_id}에 이미 외출 {len(existing)}개가 있어 중단합니다. 다시 채우려면 --force.")
        return 0

    plan = split_outings(files)
    for title, group in plan:
        outing = call("POST", "/outings", json={"pet_id": args.pet_id, "input_mode": "uploaded_audio", "title": title})
        started = datetime.fromisoformat(outing["started_at"].replace("Z", "+00:00"))
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        session = uuid.uuid4().hex
        try:
            for i, f in enumerate(group):
                label, note = classify(f)
                # 서버는 외출 시작 이후이면서 미래가 아닌 관찰만 받는다. 5초 클립이 끝난 뒤에 연결한다.
                captured = started + timedelta(seconds=0.2 + CLIP_SPACING_S * i)
                ready = captured + timedelta(seconds=CLIP_DURATION_S + 0.5)
                wait = (ready - datetime.now(timezone.utc)).total_seconds()
                if wait > 0:
                    time.sleep(wait)
                clip = call("POST", "/audio-clips/upload", data=f.read_bytes(), headers={"Content-Type": "audio/wav"},
                            params={"pet_id": args.pet_id, "store_consent": "true", "retention_days": 7,
                                    "capture_kind": "file_replay", "capture_session": session,
                                    "captured_at": captured.isoformat(),
                                    "outing_id": outing["id"], "demo_source": f"ESC-50 공개 음원 {f.name}"})
                call("POST", f"/audio-clips/{clip['id']}/review", json={"pet_id": args.pet_id, "label": label, "note": note})
                score = clip["analysis"].get("dog_score")
                print(f"  {title[:8]:8s} {f.name:18s} YAMNet Bark={score if score is None else round(score, 3)}  의견={label}", flush=True)
        finally:
            call("POST", f"/outings/{outing['id']}/end", params={"pet_id": args.pet_id})
        print(f"외출 '{title}' 완료 ({len(group)}개 클립)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
