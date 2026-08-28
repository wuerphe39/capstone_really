"""
행동 인식(YOLOv8) + 감정 분류(EfficientNet-B0) 통합 추론 파이프라인.

사용 예:
    python petmind/ai/pipeline.py          # 웹캠 실시간
    python petmind/ai/pipeline.py image.jpg  # 이미지 파일
"""
import sys
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image
from torchvision import transforms, models
from ultralytics import YOLO
import torch.nn as nn

# ── 경로 ──────────────────────────────────────────────
AI_DIR = Path(__file__).parent
BEHAVIOR_WEIGHTS = AI_DIR / "behavior" / "weights" / "behavior_v1" / "weights" / "best.pt"
EMOTION_WEIGHTS  = AI_DIR / "emotion"  / "weights" / "best.pt"

# ── 클래스 ────────────────────────────────────────────
BEHAVIOR_LABELS = ["happy", "anxious", "playing", "resting", "alert"]
EMOTION_LABELS  = ["happy", "sad", "angry", "neutral"]

# 행동-감정 조합 색상 (BGR)
LABEL_COLORS = {
    "happy":   (0, 200, 0),
    "anxious": (0, 100, 255),
    "playing": (255, 180, 0),
    "resting": (180, 180, 180),
    "alert":   (0, 0, 255),
}

EMOTION_TRANSFORM = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
])


class EmotionClassifier(nn.Module):
    def __init__(self):
        super().__init__()
        self.backbone = models.efficientnet_b0(weights=None)
        in_features = self.backbone.classifier[1].in_features
        self.backbone.classifier = nn.Sequential(
            nn.Dropout(p=0.3),
            nn.Linear(in_features, len(EMOTION_LABELS)),
        )

    def forward(self, x):
        return self.backbone(x)


class PetMindPipeline:
    def __init__(self, conf: float = 0.5):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        # 행동 인식 모델
        self.behavior_model = YOLO(str(BEHAVIOR_WEIGHTS))
        self.conf = conf

        # 감정 분류 모델
        self.emotion_model = EmotionClassifier().to(self.device)
        self.emotion_model.load_state_dict(
            torch.load(EMOTION_WEIGHTS, map_location=self.device)
        )
        self.emotion_model.eval()

        print(f"PetMind Pipeline 로드 완료 (device: {self.device})")

    def _classify_emotion(self, frame, bbox) -> dict:
        x1, y1, x2, y2 = map(int, bbox)
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return {"label": "unknown", "confidence": 0.0}
        img = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
        tensor = EMOTION_TRANSFORM(img).unsqueeze(0).to(self.device)
        with torch.no_grad():
            probs = torch.softmax(self.emotion_model(tensor), dim=1)[0]
        idx = probs.argmax().item()
        return {"label": EMOTION_LABELS[idx], "confidence": float(probs[idx])}

    def predict(self, frame) -> list[dict]:
        """
        반환값:
          [{"behavior": "playing", "behavior_conf": 0.91,
            "emotion": "happy",   "emotion_conf": 0.87,
            "bbox": [x1, y1, x2, y2]}, ...]
        """
        results = self.behavior_model(frame, conf=self.conf, verbose=False)
        output = []
        for r in results:
            for box in r.boxes:
                bbox = box.xyxy[0].tolist()
                behavior = BEHAVIOR_LABELS[int(box.cls[0])]
                behavior_conf = float(box.conf[0])
                emotion = self._classify_emotion(frame, bbox)
                output.append({
                    "behavior":      behavior,
                    "behavior_conf": behavior_conf,
                    "emotion":       emotion["label"],
                    "emotion_conf":  emotion["confidence"],
                    "bbox":          bbox,
                })
        return output

    def draw(self, frame, predictions: list[dict]):
        for p in predictions:
            x1, y1, x2, y2 = map(int, p["bbox"])
            color = LABEL_COLORS.get(p["behavior"], (255, 255, 255))
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            line1 = f"behavior: {p['behavior']} ({p['behavior_conf']:.2f})"
            line2 = f"emotion:  {p['emotion']} ({p['emotion_conf']:.2f})"
            cv2.putText(frame, line1, (x1, y1 - 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
            cv2.putText(frame, line2, (x1, y1 -  6), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
        return frame


def run_camera(source=0):
    pipeline = PetMindPipeline()
    cap = cv2.VideoCapture(source)
    print("실행 중... 종료: q")
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        preds = pipeline.predict(frame)
        frame = pipeline.draw(frame, preds)
        for p in preds:
            print(f"  [{p['behavior']}] emotion={p['emotion']}")
        cv2.imshow("PetMind", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
    cap.release()
    cv2.destroyAllWindows()


def run_image(path: str):
    pipeline = PetMindPipeline()
    frame = cv2.imread(path)
    if frame is None:
        print(f"이미지 로드 실패: {path}")
        return
    preds = pipeline.predict(frame)
    frame = pipeline.draw(frame, preds)
    print("결과:")
    for p in preds:
        print(f"  behavior={p['behavior']} ({p['behavior_conf']:.2f}), "
              f"emotion={p['emotion']} ({p['emotion_conf']:.2f})")
    cv2.imshow("PetMind", frame)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    source = sys.argv[1] if len(sys.argv) > 1 else 0
    if isinstance(source, str) and Path(source).exists():
        run_image(source)
    else:
        run_camera(int(source) if isinstance(source, str) else source)
