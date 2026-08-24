"""
수집한 짖음 음성 파일을 학습 가능한 형태로 정리.
- 지원 포맷: .wav, .mp3, .m4a → .wav 변환
- 3초 단위로 자르기 (짧은 건 zero-pad)
- 클래스별 샘플 수 출력

사용법:
  python prepare.py --input_dir ./raw_audio --output_dir ./data
"""
import argparse
from pathlib import Path

import numpy as np
import soundfile as sf
import librosa

SR = 22050
DURATION = 3.0
LABELS = ["alert", "separation_anxiety", "playing"]


def convert_and_trim(src: Path, dst_dir: Path, label: str):
    dst_dir.mkdir(parents=True, exist_ok=True)
    y, _ = librosa.load(str(src), sr=SR, mono=True)

    target_len = int(SR * DURATION)
    # DURATION보다 긴 파일은 슬라이딩 윈도우로 분할
    count = 0
    if len(y) >= target_len:
        for start in range(0, len(y) - target_len + 1, target_len):
            chunk = y[start : start + target_len]
            out_path = dst_dir / f"{src.stem}_{count:04d}.wav"
            sf.write(str(out_path), chunk, SR)
            count += 1
    else:
        # 짧은 파일은 zero-pad
        chunk = np.pad(y, (0, target_len - len(y)))
        out_path = dst_dir / f"{src.stem}_0000.wav"
        sf.write(str(out_path), chunk, SR)
        count = 1

    return count


def prepare(input_dir: Path, output_dir: Path):
    EXTS = {".wav", ".mp3", ".m4a", ".ogg"}
    total = 0

    for label in LABELS:
        label_in = input_dir / label
        label_out = output_dir / label
        if not label_in.exists():
            print(f"[경고] {label_in} 없음 — 건너뜀")
            continue

        files = [f for f in label_in.iterdir() if f.suffix.lower() in EXTS]
        count = 0
        for f in files:
            try:
                count += convert_and_trim(f, label_out, label)
            except Exception as e:
                print(f"  [오류] {f.name}: {e}")

        print(f"{label:20s}: {count}개 샘플")
        total += count

    print(f"\n총 {total}개 샘플 준비 완료 → {output_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_dir", type=Path, default=Path("./raw_audio"))
    parser.add_argument("--output_dir", type=Path, default=Path("./data"))
    args = parser.parse_args()
    prepare(args.input_dir, args.output_dir)
