from pathlib import Path
import numpy as np
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import classification_report
from feature_extract import extract_features

DATA_DIR = Path(__file__).parent / "data"
WEIGHTS_DIR = Path(__file__).parent / "weights"
WEIGHTS_DIR.mkdir(exist_ok=True)

LABELS = ["alert", "separation_anxiety", "playing"]


def load_dataset():
    features, labels = [], []
    for label in LABELS:
        label_dir = DATA_DIR / label
        if not label_dir.exists():
            print(f"Warning: {label_dir} not found, skipping")
            continue
        for audio_file in label_dir.glob("*.wav"):
            try:
                feat = extract_features(str(audio_file))
                features.append(feat)
                labels.append(label)
            except Exception as e:
                print(f"Error processing {audio_file}: {e}")
    return np.array(features), np.array(labels)


def train():
    print("Loading dataset...")
    X, y = load_dataset()
    print(f"Total samples: {len(X)}")

    le = LabelEncoder()
    y_enc = le.fit_transform(y)

    X_train, X_val, y_train, y_val = train_test_split(
        X, y_enc, test_size=0.2, random_state=42, stratify=y_enc
    )

    model = RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=-1)
    model.fit(X_train, y_train)

    y_pred = model.predict(X_val)
    print(classification_report(y_val, y_pred, target_names=le.classes_))

    joblib.dump(model, WEIGHTS_DIR / "bark_model.pkl")
    joblib.dump(le, WEIGHTS_DIR / "label_encoder.pkl")
    print("Saved model to weights/")


if __name__ == "__main__":
    train()
