from pathlib import Path
from ultralytics import YOLO
import cv2

LABELS = ["happy", "anxious", "playing", "resting", "alert"]
WEIGHTS = Path(__file__).parent / "weights" / "behavior_v1" / "weights" / "best.pt"


class BehaviorDetector:
    def __init__(self, weights: Path = WEIGHTS, conf: float = 0.5):
        self.model = YOLO(str(weights))
        self.conf = conf

    def predict(self, frame):
        results = self.model(frame, conf=self.conf, verbose=False)
        detections = []
        for r in results:
            for box in r.boxes:
                cls = int(box.cls[0])
                detections.append({
                    "label": LABELS[cls],
                    "confidence": float(box.conf[0]),
                    "bbox": box.xyxy[0].tolist(),
                })
        return detections

    def draw(self, frame, detections: list):
        for d in detections:
            x1, y1, x2, y2 = map(int, d["bbox"])
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            text = f"{d['label']} {d['confidence']:.2f}"
            cv2.putText(frame, text, (x1, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        return frame


if __name__ == "__main__":
    import sys
    source = sys.argv[1] if len(sys.argv) > 1 else 0
    detector = BehaviorDetector()
    cap = cv2.VideoCapture(source)
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        detections = detector.predict(frame)
        frame = detector.draw(frame, detections)
        cv2.imshow("Behavior", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
    cap.release()
    cv2.destroyAllWindows()
