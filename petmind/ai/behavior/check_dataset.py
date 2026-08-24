"""라벨링 완료 후 클래스별 샘플 수와 이상 여부를 확인."""
from pathlib import Path
from collections import Counter

DATA_DIR = Path(__file__).parent / "data"
LABELS = ["happy", "anxious", "playing", "resting", "alert", "sick_suspect", "hungry"]


def check(split: str):
    lbl_dir = DATA_DIR / "labels" / split
    img_dir = DATA_DIR / "images" / split
    if not lbl_dir.exists():
        return

    counts = Counter()
    no_label = []
    for img in img_dir.glob("*.*"):
        lbl = lbl_dir / (img.stem + ".txt")
        if not lbl.exists():
            no_label.append(img.name)
            continue
        for line in lbl.read_text().splitlines():
            if line.strip():
                idx = int(line.split()[0])
                counts[LABELS[idx]] += 1

    print(f"\n[{split}]")
    for label in LABELS:
        bar = "█" * (counts[label] // 10)
        print(f"  {label:15s} {counts[label]:5d}  {bar}")
    if no_label:
        print(f"  ※ 라벨 없는 이미지 {len(no_label)}개: {no_label[:5]}")


if __name__ == "__main__":
    for split in ["train", "val", "test"]:
        check(split)
