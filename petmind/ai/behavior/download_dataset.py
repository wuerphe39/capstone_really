"""
Roboflow에서 반려견 행동 탐지 데이터셋을 다운로드하고
YOLO 포맷으로 data/ 폴더에 배치.

사전 조건:
  pip install roboflow python-dotenv

사용법:
  python download_dataset.py
"""
import os
import shutil
from pathlib import Path
from dotenv import load_dotenv
from roboflow import Roboflow

load_dotenv(Path(__file__).parents[3] / ".env")

API_KEY = os.environ["ROBOFLOW_API_KEY"]
DATA_DIR = Path(__file__).parent / "data"

# Roboflow에서 검색한 공개 반려견 행동 데이터셋 목록
# https://universe.roboflow.com 에서 "dog behavior" 검색 후 원하는 것으로 교체 가능
DATASETS = [
    {
        "workspace": "dog-behavior-detection",
        "project":   "dog-behavior-yolov8",
        "version":   1,
    },
    {
        "workspace": "animal-detection-lfcae",
        "project":   "dog-pose-detection",
        "version":   1,
    },
]

# 프로젝트 라벨 → 우리 라벨 매핑 (다운받은 데이터셋 라벨명에 맞게 수정)
LABEL_MAP = {
    "tail_wagging": "happy",
    "playing":      "playing",
    "resting":      "resting",
    "crouching":    "anxious",
    "alert":        "alert",
    "sick":         "sick_suspect",
    "hungry":       "hungry",
}

OUR_LABELS = ["happy", "anxious", "playing", "resting", "alert", "sick_suspect", "hungry"]


def remap_label_file(txt_path: Path, src_labels: list[str]):
    """다운받은 데이터셋의 클래스 인덱스를 우리 인덱스로 변환."""
    lines = txt_path.read_text().strip().splitlines()
    new_lines = []
    for line in lines:
        parts = line.split()
        if not parts:
            continue
        src_idx = int(parts[0])
        if src_idx >= len(src_labels):
            continue
        src_name = src_labels[src_idx]
        mapped = LABEL_MAP.get(src_name)
        if mapped is None or mapped not in OUR_LABELS:
            continue  # 매핑 없는 라벨 제외
        our_idx = OUR_LABELS.index(mapped)
        new_lines.append(f"{our_idx} " + " ".join(parts[1:]))
    txt_path.write_text("\n".join(new_lines))


def download():
    rf = Roboflow(api_key=API_KEY)

    for ds in DATASETS:
        print(f"\n다운로드: {ds['workspace']}/{ds['project']} v{ds['version']}")
        project = rf.workspace(ds["workspace"]).project(ds["project"])
        version = project.version(ds["version"])
        dataset = version.download("yolov8", location=str(DATA_DIR / "raw_rf"))

        # 다운로드된 data.yaml에서 원본 클래스명 읽기
        import yaml
        yaml_path = Path(dataset.location) / "data.yaml"
        with open(yaml_path) as f:
            cfg = yaml.safe_load(f)
        src_labels = cfg.get("names", [])
        print(f"  원본 클래스: {src_labels}")

        # 이미지·라벨을 raw/ 폴더로 복사 후 라벨 리매핑
        for split in ["train", "valid", "test"]:
            src_img = Path(dataset.location) / split / "images"
            src_lbl = Path(dataset.location) / split / "labels"
            dst_name = "val" if split == "valid" else split

            dst_img = DATA_DIR / "raw" / "images"
            dst_lbl = DATA_DIR / "raw" / "labels"
            dst_img.mkdir(parents=True, exist_ok=True)
            dst_lbl.mkdir(parents=True, exist_ok=True)

            if src_img.exists():
                for f in src_img.iterdir():
                    shutil.copy(f, dst_img / f.name)
            if src_lbl.exists():
                for f in src_lbl.glob("*.txt"):
                    dst = dst_lbl / f.name
                    shutil.copy(f, dst)
                    remap_label_file(dst, src_labels)

        shutil.rmtree(Path(dataset.location), ignore_errors=True)

    # 클래스별 샘플 수 출력
    lbl_dir = DATA_DIR / "raw" / "labels"
    counts = {l: 0 for l in OUR_LABELS}
    for txt in lbl_dir.glob("*.txt"):
        for line in txt.read_text().splitlines():
            if line.strip():
                idx = int(line.split()[0])
                counts[OUR_LABELS[idx]] += 1
    print("\n클래스별 바운딩박스 수:")
    for name, cnt in counts.items():
        print(f"  {name:15s}: {cnt}")


if __name__ == "__main__":
    download()
