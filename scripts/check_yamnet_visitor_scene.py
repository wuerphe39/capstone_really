"""Inspect the demo's YAMNet Bark/Doorbell/Knock candidates and save embeddings."""
import hashlib
import json
from pathlib import Path

import numpy as np
import tensorflow as tf
import tensorflow_hub as hub

from scripts.extract_yamnet_bark_features import HANDLE, ROOT, CLASSES, class_indices, extract, waveform


SCENE = Path('artifacts/ai_sound_demo_20261012/visitor/doorbell_knock_then_bark.wav')


def main():
    model = hub.load(HANDLE)
    indices = class_indices(model)
    signal = waveform(SCENE)
    scores, _, _ = model(tf.convert_to_tensor(signal, tf.float32))
    selected = scores.numpy()[:, indices]
    peaks = {}
    for col, name in enumerate(CLASSES):
        rank = np.argsort(selected[:, col])[-5:][::-1]
        peaks[name] = [{'patch_start_s': round(float(i*.48), 2),
                        'score': round(float(selected[i, col]), 4)} for i in rank]
    embeddings, lengths, windows = extract(model, signal, indices)
    model_sha = hashlib.sha256((Path(hub.resolve(HANDLE))/'saved_model.pb').read_bytes()).hexdigest()
    np.savez_compressed(ROOT/'visitor_scene.npz', embeddings=embeddings,
                        lengths=lengths, scores=windows, version=np.int16(3), model_sha256=model_sha)
    report = {'input': str(SCENE), 'classes': peaks,
              'five_second_window_scores': [{name: round(float(value), 4)
                  for name, value in zip(CLASSES, row)} for row in windows],
              'note': '0.96 s patches at 0.48 s hop; scores are candidates, not exact onsets or visitor evidence'}
    (ROOT/'visitor_scene.json').write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                           encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
