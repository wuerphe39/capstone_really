"""YOLOv8 행동 인식 모델 학습."""
from pathlib import Path

import torch
from ultralytics import YOLO

DATASET_YAML = Path(__file__).parent / "dataset.yaml"
WEIGHTS_DIR = Path(__file__).parent / "weights"


def train(
    model_size: str = "n",
    epochs: int = 100,
    imgsz: int = 640,
    batch: int = 16,
    device: str = "auto",
):
    if device == "auto":
        device = "0" if torch.cuda.is_available() else "cpu"
        print(f"Device: {'GPU (cuda:0)' if device == '0' else 'CPU'}")

    model = YOLO(f"yolov8{model_size}.pt")
    results = model.train(
        data=str(DATASET_YAML),
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        device=device,
        project=str(WEIGHTS_DIR),
        name="behavior_v1",
        patience=20,
        save=True,
        val=True,
        # 클래스 불균형 대응: focal loss 강화
        # happy/anxious(~16k) vs playing/resting/alert(~2.5k) 차이를 보정
        fl_gamma=1.5,
        # 재현성
        seed=42,
        # 학습률 스케줄
        cos_lr=True,
        # 로그
        plots=True,
    )
    return results


if __name__ == "__main__":
    train()
