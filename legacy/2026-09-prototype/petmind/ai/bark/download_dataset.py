"""
공개 반려견 짖음 음성 데이터셋을 다운로드하고 패턴별 폴더로 정리.

사전 조건:
  pip install kaggle requests python-dotenv

사용법:
  python download_dataset.py
"""
import os
import shutil
import zipfile
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[3] / ".env")

os.environ["KAGGLE_USERNAME"] = os.environ["KAGGLE_USERNAME"]
os.environ["KAGGLE_KEY"] = os.environ["KAGGLE_KEY"]

from kaggle.api.kaggle_api_extended import KaggleApi  # noqa: E402

DATA_DIR = Path(__file__).parent / "data"
TMP_DIR = DATA_DIR / "_tmp"

# 사용할 Kaggle 음성 데이터셋
DATASETS = [
    "mmoreaux/audio-cats-and-dogs",     # 반려동물 음성 (개 짖음 포함)
    "rupakroy/dog-bark-dataset",        # 반려견 짖음 전용
]

# 다운로드 폴더 → 우리 패턴 매핑 (데이터셋 구조에 따라 수동 조정 필요)
# 공개 데이터셋은 alert/separation/playing 구분이 없으므로
# 자동 분류는 librosa 특징 기반 규칙으로 1차 분류 후 직접 검수 필요
PATTERN_LABELS = ["alert", "separation_anxiety", "playing"]


def auto_classify(wav_path: Path) -> str:
    """
    librosa 간단 휴리스틱으로 1차 패턴 분류.
    - 짧고 반복적 → alert
    - 길고 낮은 음조 → separation_anxiety
    - 짧고 높은 음조 → playing
    검수 후 잘못 분류된 것은 수동으로 이동할 것.
    """
    import librosa
    import numpy as np

    y, sr = librosa.load(str(wav_path), sr=22050, duration=3.0)
    if len(y) == 0:
        return "alert"

    duration = librosa.get_duration(y=y, sr=sr)
    pitches, magnitudes = librosa.piptrack(y=y, sr=sr)
    pitch_vals = pitches[magnitudes > magnitudes.mean()]
    avg_pitch = float(pitch_vals.mean()) if len(pitch_vals) > 0 else 0.0

    zcr = float(librosa.feature.zero_crossing_rate(y).mean())

    if zcr > 0.15:
        return "alert"
    elif avg_pitch < 300:
        return "separation_anxiety"
    else:
        return "playing"


def download():
    api = KaggleApi()
    api.authenticate()

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    for label in PATTERN_LABELS:
        (DATA_DIR / label).mkdir(exist_ok=True)

    for ds in DATASETS:
        print(f"\n다운로드: {ds}")
        try:
            api.dataset_download_files(ds, path=str(TMP_DIR), unzip=True)
        except Exception as e:
            print(f"  [오류] {e}")
            continue

    # wav 파일 전부 수집 → 1차 자동 분류
    wav_files = list(TMP_DIR.rglob("*.wav")) + list(TMP_DIR.rglob("*.mp3"))
    print(f"\n발견된 음성 파일: {len(wav_files)}개")
    print("1차 자동 분류 중 (librosa 휴리스틱)...")

    counts = {l: 0 for l in PATTERN_LABELS}
    for wav in wav_files:
        try:
            pattern = auto_classify(wav)
            dst = DATA_DIR / pattern / wav.name
            shutil.copy(wav, dst)
            counts[pattern] += 1
        except Exception as e:
            print(f"  [건너뜀] {wav.name}: {e}")

    shutil.rmtree(TMP_DIR, ignore_errors=True)

    print("\n1차 자동 분류 결과:")
    for label, cnt in counts.items():
        print(f"  {label:20s}: {cnt}개")
    print("\n※ 자동 분류는 부정확할 수 있습니다.")
    print("  각 폴더를 열어 잘못 분류된 파일을 수동으로 이동해 주세요.")


if __name__ == "__main__":
    download()
