"""
라벨링 완료된 이미지에 데이터 증강 적용.
images/train + labels/train 에 증강 이미지+라벨을 추가로 저장.
"""
import random
import shutil
from pathlib import Path

import cv2
import numpy as np

IMG_DIR = Path(__file__).parent / "data" / "images" / "train"
LBL_DIR = Path(__file__).parent / "data" / "labels" / "train"

AUG_FACTOR = 4  # 원본 1장당 증강 이미지 수


def flip_h(img, boxes):
    img = cv2.flip(img, 1)
    # YOLO 포맷: cx cy w h (정규화) — 좌우 반전 시 cx = 1 - cx
    boxes[:, 1] = 1.0 - boxes[:, 1]
    return img, boxes


def rotate(img, boxes, angle):
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    img = cv2.warpAffine(img, M, (w, h), borderValue=(114, 114, 114))
    # 작은 각도 회전은 bbox 근사 유지
    return img, boxes


def adjust_brightness(img, boxes, factor):
    img = np.clip(img.astype(np.float32) * factor, 0, 255).astype(np.uint8)
    return img, boxes


def adjust_contrast(img, boxes, factor):
    mean = img.mean()
    img = np.clip((img.astype(np.float32) - mean) * factor + mean, 0, 255).astype(np.uint8)
    return img, boxes


AUGMENTATIONS = [
    lambda img, b: flip_h(img, b),
    lambda img, b: rotate(img, b, random.uniform(-15, 15)),
    lambda img, b: adjust_brightness(img, b, random.uniform(0.6, 1.4)),
    lambda img, b: adjust_contrast(img, b, random.uniform(0.7, 1.3)),
]


def load_labels(lbl_path: Path) -> np.ndarray:
    if not lbl_path.exists():
        return np.zeros((0, 5))
    lines = lbl_path.read_text().strip().splitlines()
    return np.array([list(map(float, l.split())) for l in lines if l])


def save_labels(lbl_path: Path, boxes: np.ndarray):
    lines = [
        f"{int(b[0])} {b[1]:.6f} {b[2]:.6f} {b[3]:.6f} {b[4]:.6f}"
        for b in boxes
    ]
    lbl_path.write_text("\n".join(lines))


def augment():
    images = sorted(IMG_DIR.glob("*.jpg")) + sorted(IMG_DIR.glob("*.png"))
    print(f"원본 이미지 수: {len(images)}")

    generated = 0
    for img_path in images:
        img = cv2.imread(str(img_path))
        lbl_path = LBL_DIR / (img_path.stem + ".txt")
        boxes = load_labels(lbl_path).copy()

        for i in range(AUG_FACTOR):
            aug_fn = random.choice(AUGMENTATIONS)
            aug_img, aug_boxes = aug_fn(img.copy(), boxes.copy())

            stem = f"{img_path.stem}_aug{i}"
            cv2.imwrite(str(IMG_DIR / f"{stem}.jpg"), aug_img)
            if aug_boxes.shape[0] > 0:
                save_labels(LBL_DIR / f"{stem}.txt", aug_boxes)
            generated += 1

    print(f"증강 완료 — 생성된 이미지 수: {generated}")
    print(f"전체 학습 이미지 수: {len(images) + generated}")


if __name__ == "__main__":
    augment()
