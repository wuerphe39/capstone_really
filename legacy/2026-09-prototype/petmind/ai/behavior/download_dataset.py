"""
Roboflow에서 반려견 행동/자세 데이터셋을 다운로드하고
YOLO 포맷으로 data/raw/ 폴더에 배치.

클래스 (5개):
  0: happy  1: anxious  2: playing  3: resting  4: alert

사용법:
  python download_dataset.py
"""
import os
import shutil
from pathlib import Path
from dotenv import load_dotenv, find_dotenv
from roboflow import Roboflow
import yaml

load_dotenv(find_dotenv(usecwd=True))

API_KEY = os.getenv("ROBOFLOW_API_KEY", "")
DATA_DIR = Path(__file__).parent / "data"

DATASETS = [
    {
        "workspace": "dog-pose-annotation",
        "project":   "dog-pose-feaal",
        "version":   12,
    },
]

OUR_LABELS = ["happy", "anxious", "playing", "resting", "alert"]

LABEL_MAP = {
    # dog-pose-feaal (프랑스어)
    "chien assis":   "resting",
    "chien debout":  "alert",
    "chien a pieds": "playing",
    # 영어 대비
    "sit":           "resting",
    "stand":         "alert",
    "lay":           "resting",
    "playing":       "playing",
    "run":           "playing",
    "happy":         "happy",
    "anxious":       "anxious",
    "fearful":       "anxious",
    "sad":           "anxious",
}


def remap_label_file(txt_path: Path, src_labels: list):
    lines = txt_path.read_text(encoding="utf-8").strip().splitlines()
    new_lines = []
    for line in lines:
        parts = line.split()
        if not parts:
            continue
        src_idx = int(parts[0])
        if src_idx >= len(src_labels):
            continue
        src_name = src_labels[src_idx].lower()
        mapped = LABEL_MAP.get(src_name)
        if not mapped or mapped not in OUR_LABELS:
            continue
        our_idx = OUR_LABELS.index(mapped)
        new_lines.append(f"{our_idx} " + " ".join(parts[1:]))
    txt_path.write_text("\n".join(new_lines), encoding="utf-8")


def download():
    if not API_KEY:
        print("[오류] .env에 ROBOFLOW_API_KEY가 없습니다.")
        return

    print(f"API 키 확인: {API_KEY[:6]}...")
    rf = Roboflow(api_key=API_KEY)

    dst_img = DATA_DIR / "raw" / "images"
    dst_lbl = DATA_DIR / "raw" / "labels"
    dst_img.mkdir(parents=True, exist_ok=True)
    dst_lbl.mkdir(parents=True, exist_ok=True)

    success = 0
    for ds in DATASETS:
        print(f"\n다운로드: {ds['workspace']}/{ds['project']} v{ds['version']}")
        try:
            project = rf.workspace(ds["workspace"]).project(ds["project"])
            version = project.version(ds["version"])
            tmp_dir = DATA_DIR / "_tmp_rf"
            dataset = version.download("yolov8", location=str(tmp_dir))

            with open(Path(dataset.location) / "data.yaml", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            src_labels = cfg.get("names", [])
            print(f"  원본 클래스: {src_labels}")

            for split in ["train", "valid", "test"]:
                src_img = Path(dataset.location) / split / "images"
                src_lbl = Path(dataset.location) / split / "labels"
                if src_img.exists():
                    for f in src_img.iterdir():
                        shutil.copy(f, dst_img / f.name)
                if src_lbl.exists():
                    for f in src_lbl.glob("*.txt"):
                        dst = dst_lbl / f.name
                        shutil.copy(f, dst)
                        remap_label_file(dst, src_labels)

            shutil.rmtree(tmp_dir, ignore_errors=True)
            success += 1
            print(f"  완료!")

        except Exception as e:
            print(f"  [오류] {e}")

    print_summary(dst_lbl)


def print_summary(lbl_dir: Path):
    counts = {l: 0 for l in OUR_LABELS}
    for txt in lbl_dir.glob("*.txt"):
        for line in txt.read_text(encoding="utf-8").splitlines():
            if line.strip():
                idx = int(line.split()[0])
                if idx < len(OUR_LABELS):
                    counts[OUR_LABELS[idx]] += 1

    print("\n=== 현재 클래스별 바운딩박스 수 ===")
    for name, cnt in counts.items():
        bar = "█" * (cnt // 20)
        status = "✅" if cnt >= 200 else "❌"
        print(f"  {status} {name:10s} {cnt:5d}  {bar}")


if __name__ == "__main__":
    download()
