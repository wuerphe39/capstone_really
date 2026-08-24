from ultralytics import YOLO


def train(
    model_size: str = "n",
    epochs: int = 100,
    imgsz: int = 640,
    batch: int = 16,
    device: str = "0",
):
    model = YOLO(f"yolov8{model_size}.pt")
    results = model.train(
        data="dataset.yaml",
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        device=device,
        project="weights",
        name="behavior_v1",
        patience=20,
        save=True,
        val=True,
    )
    return results


if __name__ == "__main__":
    train()
