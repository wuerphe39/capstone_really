"""
Roboflow에서 반려견 감정 데이터셋을 다운로드하고
emotion/data/{train,val,test}/{class}/ 구조로 정리.

데이터셋: dog-emotion-zaveh/dog-emotion-ovhny (17,872장)
  클래스: happy / relaxed(→neutral) / sad / angry

사용법:
  python download_dataset.py
"""
import os
import shutil
from pathlib import Path
from dotenv import load_dotenv, find_dotenv
from roboflow import Roboflow
from PIL import Image

load_dotenv(find_dotenv(usecwd=True))

API_KEY = os.getenv("ROBOFLOW_API_KEY", "")
DATA_DIR = Path(__file__).parent / "data"

WORKSPACE = "dog-emotion-zaveh"
PROJECT   = "dog-emotion-ovhny"
VERSION   = 2

# 다운받은 클래스 → 우리 클래스 매핑
LABEL_MAP = {
    "happy":   "happy",
    "relaxed": "neutral",
    "sad":     "sad",
    "angry":   "angry",
}
OUR_LABELS = ["happy", "sad", "angry", "neutral"]


def crop_and_save(img_path: Path, txt_path: Path, split: str, class_names: list):
    """YOLO 바운딩박스 기준으로 개 영역을 잘라 클래스 폴더에 저장."""
    if not txt_path.exists():
        return
    img = Image.open(img_path).convert("RGB")
    w, h = img.size

    for i, line in enumerate(txt_path.read_text().splitlines()):
        parts = line.strip().split()
        if not parts:
            continue
        cls_idx = int(parts[0])
        if cls_idx >= len(class_names):
            continue
        src_name = class_names[cls_idx]
        mapped = LABEL_MAP.get(src_name)
        if not mapped:
            continue

        cx, cy, bw, bh = map(float, parts[1:5])
        x1 = int((cx - bw / 2) * w)
        y1 = int((cy - bh / 2) * h)
        x2 = int((cx + bw / 2) * w)
        y2 = int((cy + bh / 2) * h)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)

        if x2 <= x1 or y2 <= y1:
            continue

        crop = img.crop((x1, y1, x2, y2))
        dst_dir = DATA_DIR / split / mapped
        dst_dir.mkdir(parents=True, exist_ok=True)
        crop.save(dst_dir / f"{img_path.stem}_{i}.jpg")


def download():
    if not API_KEY:
        print("[오류] .env에 ROBOFLOW_API_KEY가 없습니다.")
        return

    print(f"API 키 확인: {API_KEY[:6]}...")
    rf = Roboflow(api_key=API_KEY)

    print(f"\n다운로드: {WORKSPACE}/{PROJECT} v{VERSION}")
    project = rf.workspace(WORKSPACE).project(PROJECT)
    version = project.version(VERSION)
    tmp_dir = DATA_DIR / "_tmp"
    dataset = version.download("yolov8", location=str(tmp_dir))

    import yaml
    with open(Path(dataset.location) / "data.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    class_names = cfg.get("names", [])
    print(f"원본 클래스: {class_names}")

    print("\n바운딩박스 기준으로 이미지 크롭 중...")
    split_map = {"train": "train", "valid": "val", "test": "test"}
    counts = {l: 0 for l in OUR_LABELS}

    for src_split, dst_split in split_map.items():
        img_dir = Path(dataset.location) / src_split / "images"
        lbl_dir = Path(dataset.location) / src_split / "labels"
        if not img_dir.exists():
            continue
        for img_path in img_dir.iterdir():
            txt_path = lbl_dir / (img_path.stem + ".txt")
            before = sum(counts.values())
            crop_and_save(img_path, txt_path, dst_split, class_names)
            after = sum(counts.values())

    shutil.rmtree(tmp_dir, ignore_errors=True)

    # 실제 저장된 파일 수 집계
    print("\n=== 다운로드 완료 ===")
    for split in ["train", "val", "test"]:
        split_dir = DATA_DIR / split
        if not split_dir.exists():
            continue
        row = []
        for label in OUR_LABELS:
            cnt = len(list((split_dir / label).glob("*.jpg"))) if (split_dir / label).exists() else 0
            row.append(f"{label}:{cnt}")
        print(f"  {split:5s} → " + "  ".join(row))


if __name__ == "__main__":
    download()
