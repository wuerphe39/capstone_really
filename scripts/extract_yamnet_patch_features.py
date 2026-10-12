"""Extract full 10-second YAMNet patch sequences for strong-label experiments."""
import argparse
import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '2')
import numpy as np
import tensorflow as tf
import tensorflow_hub as hub

from scripts.extract_yamnet_bark_features import HANDLE, waveform


def main(root):
    manifest_path = root/'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    output = root/'patch_features'
    output.mkdir(parents=True, exist_ok=True)
    tf.config.threading.set_intra_op_parallelism_threads(2)
    model = hub.load(HANDLE)
    model_sha = hashlib.sha256((Path(hub.resolve(HANDLE))/'saved_model.pb').read_bytes()).hexdigest()
    count = 0
    for rows in manifest['rows'].values():
        for row in rows:
            destination = output/(row['sha256']+'.npz')
            if destination.exists():
                with np.load(destination) as cached:
                    if int(cached['version']) == 1 and str(cached['model_sha256']) == model_sha:
                        count += 1
                        continue
            source = Path(row['path'])
            if hashlib.sha256(source.read_bytes()).hexdigest() != row['sha256']:
                raise ValueError(f'source hash mismatch: {row["clip_id"]}')
            scores, embeddings, _ = model(tf.constant(waveform(source), tf.float32))
            patches = embeddings.numpy().astype(np.float16)
            bark = scores.numpy()[:, 70].astype(np.float32)
            if not 18 <= len(patches) <= 21:
                raise ValueError(f'unexpected 10-second patch count: {row["clip_id"]}')
            np.savez_compressed(destination, embeddings=patches, bark_scores=bark,
                                model_sha256=model_sha, version=np.int16(1))
            count += 1
    record = {'handle': HANDLE, 'model_sha256': model_sha,
              'manifest_sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
              'patch_s': .96, 'hop_s': .48, 'files': count}
    (root/'patch_extraction.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    print(record, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    main(parser.parse_args().root)
