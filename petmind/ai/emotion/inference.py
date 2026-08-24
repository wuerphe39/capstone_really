from pathlib import Path
import torch
from torchvision import transforms
from PIL import Image
import cv2
import numpy as np
from model import EmotionClassifier, LABELS

WEIGHTS = Path(__file__).parent / "weights" / "best.pt"

TRANSFORM = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
])


class EmotionPredictor:
    def __init__(self, weights: Path = WEIGHTS):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = EmotionClassifier().to(self.device)
        self.model.load_state_dict(torch.load(weights, map_location=self.device))
        self.model.eval()

    def predict(self, frame) -> dict:
        img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        tensor = TRANSFORM(img).unsqueeze(0).to(self.device)
        with torch.no_grad():
            logits = self.model(tensor)
            probs = torch.softmax(logits, dim=1)[0]
        idx = probs.argmax().item()
        return {"label": LABELS[idx], "confidence": float(probs[idx])}
