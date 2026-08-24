import numpy as np
import librosa

SR = 22050
DURATION = 3.0
N_MFCC = 40
N_MELS = 128
HOP_LENGTH = 512


def extract_features(audio_path: str) -> np.ndarray:
    y, sr = librosa.load(audio_path, sr=SR, duration=DURATION)
    y, _ = librosa.effects.trim(y, top_db=20)

    # 길이 고정 (부족하면 zero-pad)
    target_len = int(SR * DURATION)
    if len(y) < target_len:
        y = np.pad(y, (0, target_len - len(y)))
    else:
        y = y[:target_len]

    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=N_MFCC, hop_length=HOP_LENGTH)
    mfcc_delta = librosa.feature.delta(mfcc)
    mel = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=N_MELS, hop_length=HOP_LENGTH)
    mel_db = librosa.power_to_db(mel, ref=np.max)

    mfcc_feat = np.concatenate([mfcc.mean(axis=1), mfcc.std(axis=1)])
    mfcc_delta_feat = np.concatenate([mfcc_delta.mean(axis=1), mfcc_delta.std(axis=1)])
    mel_feat = np.concatenate([mel_db.mean(axis=1), mel_db.std(axis=1)])

    return np.concatenate([mfcc_feat, mfcc_delta_feat, mel_feat])
