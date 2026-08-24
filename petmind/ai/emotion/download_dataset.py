"""
Kaggle에서 반려동물 감정 데이터셋을 다운로드하고
emotion/data/{train,val,test}/{class}/ 구조로 정리.

사전 조건:
  pip install kaggle python-dotenv
  .env 에 KAGGLE_USERNAME, KAGGLE_KEY 설정

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
TMP_DIR = Path(__file__).parent / "data" / "_tmp"

# 사용할 Kaggle 데이터셋 목록
# https://www.kaggle.com/datasets 에서 "dog emotion" 검색 후 교체 가능
DATASETS = [
    "anshtanwar/pets-facial-expression-dataset",  # 행복·슬픔·화남·무표정
]

# 다운로드된 폴더명 → 우리 클래스명 매핑
LABEL_MAP = {
    "happy":   "happy",
    "sad":     "sad",
    "angry":   "angry",
    "neutral": "neutral",
    # 데이터셋마다 폴더명이 다를 수 있으니 추가
    "Happy":   "happy",
    "Sad":     "sad",
    "Angry":   "angry",
    "Neutral": "neutral",
}

SPLITS = ["train", "val", "test"]
SPLIT_RATIO = (0.7, 0.2, 0.1)


def organize(src_root: Path):
    import random
    from math import floor

    for label_dir in src_root.rglob("*"):
        if not label_dir.is_dir():
            continue
        mapped = LABEL_MAP.get(label_dir.name)
        if mapped is None:
            continue

        images = list(label_dir.glob("*.jpg")) + list(label_dir.glob("*.png")) + list(label_dir.glob("*.jpeg"))
        random.shuffle(images)
        n = len(images)
        n_train = floor(n * SPLIT_RATIO[0])
        n_val   = floor(n * SPLIT_RATIO[1])

        split_imgs = {
            "train": images[:n_train],
            "val":   images[n_train:n_train + n_val],
            "test":  images[n_train + n_val:],
        }

        for split, imgs in split_imgs.items():
            dst = DATA_DIR / split / mapped
            dst.mkdir(parents=True, exist_ok=True)
            for img in imgs:
                shutil.copy(img, dst / img.name)

        print(f"  {mapped}: train={len(split_imgs['train'])} val={len(split_imgs['val'])} test={len(split_imgs['test'])}")


def download():
    api = KaggleApi()
    api.authenticate()

    TMP_DIR.mkdir(parents=True, exist_ok=True)

    for ds in DATASETS:
        print(f"\n다운로드: {ds}")
        api.dataset_download_files(ds, path=str(TMP_DIR), unzip=True)

    print("\n클래스별 정리 중...")
    organize(TMP_DIR)

    shutil.rmtree(TMP_DIR, ignore_errors=True)
    print("\n완료!")

    # 결과 요약
    for split in SPLITS:
        split_dir = DATA_DIR / split
        if not split_dir.exists():
            continue
        counts = {d.name: len(list(d.iterdir())) for d in split_dir.iterdir() if d.is_dir()}
        total = sum(counts.values())
        print(f"{split:5s}: {total}장  {counts}")


if __name__ == "__main__":
    download()
