"""Fixed-prompt pretrained CLAP comparison; no test-driven prompt/threshold tuning.

Pretraining overlap cannot be ruled out. This is NOT an independent generalization
claim. Model embeddings and scores are local artifacts, not user data uploads.
"""
import argparse
import hashlib
import json
from math import gcd
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from scipy.signal import resample_poly

from pet_monitor.audio_lstm import binary_metrics

REVISION = '8fa0f1c6d0433df6e97c127f64b2a1d6c0dcda8a'
MODEL_DIR = Path('artifacts/models/clap')


def main():
    from huggingface_hub import snapshot_download
    from transformers import ClapModel, ClapProcessor
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset',choices=['esc50','fsd50k'],default='fsd50k')
    args = parser.parse_args()
    snapshot_download('laion/clap-htsat-unfused',revision=REVISION,local_dir=MODEL_DIR,
                      allow_patterns=['*.json','*.txt','*.bin','README.md'])
    torch.set_num_threads(2); torch.manual_seed(20261011); np.random.seed(20261011)
    processor = ClapProcessor.from_pretrained(MODEL_DIR,local_files_only=True)
    model = ClapModel.from_pretrained(MODEL_DIR,local_files_only=True,weights_only=True).eval()
    esc = json.loads(Path('artifacts/datasets/esc50/manifest.json').read_text())
    categories = sorted({r['category'] for r in esc['records']})
    prompts = ['The sound of '+category.replace('_',' ')+'.' for category in categories]
    dog_index = categories.index('dog')
    with torch.inference_mode():
        text_features = model.get_text_features(**processor(text=prompts,return_tensors='pt',padding=True))
    text_features = torch.nn.functional.normalize(text_features,dim=-1)
    if args.dataset == 'esc50':
        root = Path('artifacts/datasets/esc50/audio')
        records = [{**r,'expected':int(r['category']=='dog')} for r in esc['records'] if r['split']=='test']
    else:
        root = Path('artifacts/datasets/fsd50k/eval_subset')
        records = json.loads((root/'manifest.json').read_text(encoding='utf-8'))['records']
    results = []
    cache = Path('artifacts/audio_lstm/clap_features'); cache.mkdir(parents=True,exist_ok=True)
    for i,row in enumerate(records,1):
        path = root/row['filename']
        if hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']: raise ValueError('checksum mismatch')
        cached = cache/(row['sha256']+'-'+REVISION[:8]+'.npy')
        if cached.exists():
            audio_features = torch.from_numpy(np.load(cached,allow_pickle=False))
        else:
            values,rate = sf.read(path,dtype='float32',always_2d=True)
            divisor = gcd(rate,48000)
            audio = resample_poly(values.mean(1),48000//divisor,rate//divisor).astype(np.float32)
            # Explicit nonoverlapping 10 s chunks avoid random crop selection.
            chunks = [audio[start:start+480000] for start in range(0,len(audio),480000)]
            with torch.inference_mode():
                inputs = processor(audios=chunks,sampling_rate=48000,return_tensors='pt')
                audio_features = model.get_audio_features(**inputs)
            np.save(cached,audio_features.numpy(),allow_pickle=False)
        similarity = torch.nn.functional.normalize(audio_features,dim=-1)@text_features.T
        other = torch.cat([similarity[:,:dog_index],similarity[:,dog_index+1:]],dim=1).max(1).values
        margin = float((similarity[:,dog_index]-other).max())
        results.append({'filename':row['filename'],'sha256':row['sha256'],'expected':row['expected'],
                        'dog_margin':margin,'windows':len(audio_features)})
        if i%10 == 0: print(f'CLAP {args.dataset} {i}/{len(records)}',flush=True)
    report = {'model':'laion/clap-htsat-unfused','revision':REVISION,'license':'Apache-2.0 per model card',
        'checkpoint_sha256':hashlib.sha256((MODEL_DIR/'pytorch_model.bin').read_bytes()).hexdigest(),
        'prompts':prompts,'decision':'Dog cosine similarity exceeds all other ESC class prompts in any 10-second window',
        'metrics':binary_metrics([r['expected'] for r in results],[r['dog_margin'] for r in results],0),
        'records':results,'promoted':False,
        'limitations':['pretraining overlap with ESC/Freesound cannot be ruled out; not independent validation',
                       'fixed prompts, no task-specific fine tuning; margin is not probability',
                       'clip-level Dog detection, not onset/offset, emotion or individual identity']}
    Path(f'docs/evidence/clap_{args.dataset}_comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report['metrics']),flush=True)


if __name__ == '__main__':
    main()
