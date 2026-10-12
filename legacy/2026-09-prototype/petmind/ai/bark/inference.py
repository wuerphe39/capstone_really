from pathlib import Path
import numpy as np
import joblib
import sounddevice as sd
import soundfile as sf
from feature_extract import extract_features, SR, DURATION

WEIGHTS_DIR = Path(__file__).parent / "weights"


class BarkClassifier:
    def __init__(self):
        self.model = joblib.load(WEIGHTS_DIR / "bark_model.pkl")
        self.le = joblib.load(WEIGHTS_DIR / "label_encoder.pkl")

    def predict_file(self, audio_path: str) -> dict:
        feat = extract_features(audio_path).reshape(1, -1)
        proba = self.model.predict_proba(feat)[0]
        idx = proba.argmax()
        return {
            "label": self.le.inverse_transform([idx])[0],
            "confidence": float(proba[idx]),
        }

    def predict_mic(self) -> dict:
        audio = sd.rec(int(SR * DURATION), samplerate=SR, channels=1, dtype="float32")
        sd.wait()
        tmp = "/tmp/bark_tmp.wav"
        sf.write(tmp, audio, SR)
        return self.predict_file(tmp)


if __name__ == "__main__":
    clf = BarkClassifier()
    print("Recording 3 seconds...")
    result = clf.predict_mic()
    print(f"Bark pattern: {result['label']} ({result['confidence']:.2%})")
