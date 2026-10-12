"""
감정 데이터셋의 sad 이미지를 anxious 클래스로 behavior raw 폴더에 병합.

OUR_LABELS = ["happy", "anxious", "playing", "resting", "alert"]
anxious index = 1

사용법:
  python merge_emotion_sad.py
"""
import shutil
from pathlib import Path

EMOTION_DIR = Path(__file__).parent.parent / "emotion" / "data"
BEHAVIOR_RAW_IMG = Path(__file__).parent / "data" / "raw" / "images"
BEHAVIOR_RAW_LBL = Path(__file__).parent / "data" / "raw" / "labels"

OUR_LABELS = ["happy", "anxious", "playing", "resting", "alert"]
ANXIOUS_IDX = OUR_LABELS.index("anxious")  # 1


def merge():
    BEHAVIOR_RAW_IMG.mkdir(parents=True, exist_ok=True)
    BEHAVIOR_RAW_LBL.mkdir(parents=True, exist_ok=True)

    total = 0
    for split in ["train", "val", "test"]:
        src_dir = EMOTION_DIR / split / "sad"
        if not src_dir.exists():
            continue

        images = list(src_dir.glob("*.jpg")) + list(src_dir.glob("*.png"))
        for img_path in images:
            new_name = f"em_anxious_{img_path.name}"
            shutil.copy(img_path, BEHAVIOR_RAW_IMG / new_name)
            lbl_path = BEHAVIOR_RAW_LBL / (Path(new_name).stem + ".txt")
            lbl_path.write_text(f"{ANXIOUS_IDX} 0.5 0.5 1.0 1.0\n", encoding="utf-8")
            total += 1

        print(f"  {split:5s}: {len(images)}장 복사 (sad → anxious)")

    print(f"\n완료 — 총 {total}장 추가")
    print_summary()


def print_summary():
    counts = {l: 0 for l in OUR_LABELS}
    for txt in BEHAVIOR_RAW_LBL.glob("*.txt"):
        for line in txt.read_text(encoding="utf-8").splitlines():
            if line.strip():
                idx = int(line.split()[0])
                if idx < len(OUR_LABELS):
                    counts[OUR_LABELS[idx]] += 1

    print("\n현재 behavior raw 클래스별 바운딩박스 수:")
    for name, cnt in counts.items():
        bar = "█" * (cnt // 50)
        status = "✅" if cnt >= 200 else "❌"
        print(f"  {status} {name:10s} {cnt:5d}  {bar}")


if __name__ == "__main__":
    merge()
