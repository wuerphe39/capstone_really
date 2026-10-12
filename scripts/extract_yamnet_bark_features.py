"""Extract frozen official YAMNet patch embeddings in an isolated TF environment.

Run after prepare_yamnet_bark_experiment with the artifacts/yamnet_env Python.
No labels are used for extraction or normalization.
"""
import csv
import argparse
import hashlib
import json
import os
import time
from math import gcd
from pathlib import Path

os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '2')
import numpy as np
import soundfile as sf
import tensorflow as tf
import tensorflow_hub as hub
from scipy.signal import resample_poly


ROOT = Path('artifacts/yamnet_bark_experiment')
HANDLE = 'https://tfhub.dev/google/yamnet/1'
RATE = 16000
WINDOW_S = 5
PATCH_HOP_S = .48
CLASSES = ('Bark', 'Doorbell', 'Knock')


def waveform(path):
    data, rate = sf.read(path, dtype='float32', always_2d=True)
    if len(data) == 0 or not np.isfinite(data).all():
        raise ValueError(f'invalid audio: {path}')
    mono = data.mean(axis=1)
    if rate != RATE:
        divisor = gcd(rate, RATE)
        mono = resample_poly(mono, RATE // divisor, rate // divisor)
    return mono.astype(np.float32)


def class_indices(model):
    with tf.io.gfile.GFile(model.class_map_path().numpy().decode(), 'r') as stream:
        names = {row['display_name']: int(row['index']) for row in csv.DictReader(stream)}
    return [names[name] for name in CLASSES]


def extract(model, signal, indices):
    nwin = (len(signal) + RATE*WINDOW_S - 1) // (RATE*WINDOW_S)
    lengths = []
    patches = []
    class_scores = []
    for index in range(nwin):
        chunk = signal[index*RATE*WINDOW_S:(index+1)*RATE*WINDOW_S]
        chunk = np.pad(chunk, (0, RATE*WINDOW_S-len(chunk)))
        scores, embedding, _ = model(tf.convert_to_tensor(chunk, tf.float32))
        part = embedding.numpy()
        patches.append(part)
        lengths.append(len(part))
        class_scores.append(scores.numpy()[:, indices].max(axis=0))
    return (np.concatenate(patches).astype(np.float16),
            np.asarray(lengths, dtype=np.int16),
            np.asarray(class_scores, dtype=np.float32))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.root
    manifest_path = root/'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    folder = root/'features'
    folder.mkdir(parents=True, exist_ok=True)
    tf.config.threading.set_intra_op_parallelism_threads(2)
    model = hub.load(HANDLE)
    model_path = Path(hub.resolve(HANDLE))/'saved_model.pb'
    model_sha = hashlib.sha256(model_path.read_bytes()).hexdigest()
    indices = class_indices(model)
    count = 0
    start = time.perf_counter()
    for rows in manifest['rows'].values():
        for row in rows:
            destination = folder/(row['sha256']+'.npz')
            if destination.exists():
                with np.load(destination) as cached:
                    if ('version' in cached and int(cached['version']) == 3 and
                            'model_sha256' in cached and str(cached['model_sha256']) == model_sha):
                        count += 1
                        continue
            source = Path(row['path'])
            if hashlib.sha256(source.read_bytes()).hexdigest() != row['sha256']:
                raise ValueError(f'checksum mismatch: {row["id"]}')
            embeddings, lengths, scores = extract(model, waveform(source), indices)
            np.savez_compressed(destination, embeddings=embeddings, lengths=lengths,
                                scores=scores, version=np.int16(3), model_sha256=model_sha)
            count += 1
            if count % 25 == 0:
                print(f'{count} files; {time.perf_counter()-start:.1f}s', flush=True)
    record = {'handle': HANDLE, 'tensorflow': tf.__version__,
              'model_sha256': model_sha,
              'manifest_sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
              'classes': dict(zip(CLASSES, indices)),
              'patch_hop_s': PATCH_HOP_S, 'window_s': WINDOW_S,
              'files': count, 'elapsed_s': time.perf_counter()-start}
    (root/'extraction.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    print(record, flush=True)


if __name__ == '__main__':
    main()
