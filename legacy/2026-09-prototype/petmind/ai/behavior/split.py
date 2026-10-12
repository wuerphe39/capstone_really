"""
raw/ 폴더에 수집한 원본 이미지+라벨을 train/val/test로 분할.

사용법:
  python split.py --ratio 0.7 0.2 0.1
"""
import argparse
import random
import shutil
from pathlib import Path

RAW_IMG = Path(__file__).parent / "data" / "raw" / "images"
RAW_LBL = Path(__file__).parent / "data" / "raw" / "labels"

SPLITS = ["train", "val", "test"]


def split(ratios: list[float]):
    assert abs(sum(ratios) - 1.0) < 1e-6, "비율 합이 1이어야 합니다"

    images = sorted(RAW_IMG.glob("*.jpg")) + sorted(RAW_IMG.glob("*.png"))
    random.shuffle(images)
    total = len(images)
    if total == 0:
        print("raw/images 에 이미지가 없습니다.")
        return

    n_train = int(total * ratios[0])
    n_val = int(total * ratios[1])
    splits_data = {
        "train": images[:n_train],
        "val":   images[n_train : n_train + n_val],
        "test":  images[n_train + n_val :],
    }

    base = Path(__file__).parent / "data"
    for split_name, imgs in splits_data.items():
        img_dst = base / "images" / split_name
        lbl_dst = base / "labels" / split_name
        img_dst.mkdir(parents=True, exist_ok=True)
        lbl_dst.mkdir(parents=True, exist_ok=True)

        for img_path in imgs:
            shutil.copy(img_path, img_dst / img_path.name)
            lbl_path = RAW_LBL / (img_path.stem + ".txt")
            if lbl_path.exists():
                shutil.copy(lbl_path, lbl_dst / lbl_path.name)

        print(f"{split_name:5s}: {len(imgs)}장")

    print(f"\n총 {total}장 분할 완료")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ratio", nargs=3, type=float, default=[0.7, 0.2, 0.1],
                        metavar=("TRAIN", "VAL", "TEST"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    random.seed(args.seed)
    split(args.ratio)
