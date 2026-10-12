"""Fine-tune the current LSTM on train-only barking plus household noise.

Validation chooses a candidate. Previously inspected FSD eval only audits it.
All FSD labels remain weak clip-level labels.
"""
import copy
import hashlib
import io
import json
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from torch.nn import functional as F

from pet_monitor.audio_lstm import AudioClassifier, AudioPredictor, binary_metrics, logmel
from scripts.compare_audio_lstm import _wave, checked_features, groups, scores
from scripts.train_audio_mil import bag_logits

ROOT = Path('artifacts/household_bark_20261012')
MODEL = Path('artifacts/audio_lstm/esc50_lstm.pt')
CANDIDATE = Path('artifacts/audio_lstm/household_bark_candidate.pt')
HOME = {'Door','Speech','Chatter','Domestic_sounds_and_home_sounds','Bell',
        'Wind_chime','Dishes','Vacuum_cleaner','Dishes_and_pots_and_pans'}
SEED = 20261012


def bark(row):
    return 'Bark' in row['labels']


def household_negative(row):
    return not row['expected'] and bool(HOME.intersection(row['labels']))


def mixed_features(source, noise, scale, *, offset=0):
    """Add noise at a fixed RMS fraction; keep all source windows as one MIL bag."""
    signal = _wave(source['path']).copy()
    background = _wave(noise['path'])
    if len(signal) == 0 or len(background) == 0:
        raise ValueError('empty public audio')
    background = np.resize(np.roll(background,offset),len(signal))
    rms = lambda a: float(np.sqrt(np.mean(a*a)+1e-12))
    waveform = signal + background*(scale*rms(signal)/rms(background))
    peak = float(np.abs(waveform).max())
    if peak > .99: waveform *= .99/peak
    bags=[]
    for start in range(0,len(waveform),16000*5):
        stream=io.BytesIO()
        sf.write(stream,waveform[start:start+16000*5],16000,format='WAV',subtype='FLOAT')
        stream.seek(0)
        bags.append(logmel(stream))
    return torch.stack(bags)


def group_metrics(model,bags,rows,mean,std,threshold):
    return binary_metrics([r['expected'] for r in rows],scores(model,bags,mean,std),threshold)


def main():
    torch.set_num_threads(2)
    torch.manual_seed(SEED)
    rows=groups()  # official partition, source IDs and hashes disjoint
    saved=torch.load(MODEL,map_location='cpu',weights_only=True)
    mean,std=saved['mean'],saved['std']
    train=rows['fsd_train']
    val=rows['fsd_val']
    train_bark=[r for r in train if bark(r)]
    val_bark=[r for r in val if bark(r)]
    train_noise=[r for r in train if household_negative(r)]
    val_noise=[r for r in val if household_negative(r)]
    if min(map(len,(train_bark,val_bark,train_noise,val_noise))) == 0:
        raise ValueError('insufficient disjoint Bark/household sources')
    # Explicit source grouping and checksums are validated before feature extraction.
    all_train=checked_features(train)
    original_val={s:checked_features(rows[s]) for s in ('esc_val','fsd_val')}
    mixed_train=[]
    for i,source in enumerate(train_bark):
        for j,scale in enumerate((.2,.4,.8)):
            noise=train_noise[(i*3+j)%len(train_noise)]
            mixed_train.append(mixed_features(source,noise,scale,offset=(i+j)*1600))
    # All validation positives and all household negatives; deterministic order.
    # A positive bag means the recording has a Bark label, not every window does.
    mixed_val_rows=val_bark+val_noise
    mixed_val=[]
    for i,source in enumerate(val_bark):
        mixed_val.append(mixed_features(source,val_noise[i%len(val_noise)],.4,offset=i*1600))
    mixed_val += checked_features(val_noise)
    x_train=[(b-mean)/std for b in all_train+mixed_train]
    labels=torch.tensor([r['expected'] for r in train]+[1]*len(mixed_train),dtype=torch.float32)
    pos_weight=float((labels==0).sum()/(labels==1).sum())
    model=AudioClassifier('lstm');model.load_state_dict(saved['state_dict'])
    optimizer=torch.optim.Adam(model.parameters(),lr=.0001)
    threshold=float(saved['threshold'])
    baseline=AudioClassifier('lstm');baseline.load_state_dict(saved['state_dict'])
    baseline_val={s:group_metrics(baseline,original_val[s],rows[s],mean,std,threshold) for s in original_val}
    baseline_mixed=group_metrics(baseline,mixed_val,mixed_val_rows,mean,std,threshold)
    best=None;history=[]
    for epoch in range(1,7):
        model.train()
        order=torch.randperm(len(x_train)).tolist()
        for start in range(0,len(order),12):
            indices=order[start:start+12]
            optimizer.zero_grad()
            bags=[x_train[i] for i in indices]
            logits=bag_logits(model(torch.cat(bags)),[len(b) for b in bags])
            loss=F.binary_cross_entropy_with_logits(logits,labels[indices],
                                                     pos_weight=torch.tensor(pos_weight))
            loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),5);optimizer.step()
        current={s:group_metrics(model,original_val[s],rows[s],mean,std,threshold) for s in original_val}
        mixed=group_metrics(model,mixed_val,mixed_val_rows,mean,std,threshold)
        feasible=(all(current[s]['false_positive_rate'] <= baseline_val[s]['false_positive_rate']+.05
                      for s in current) and
                  mixed['false_positive_rate'] <= baseline_mixed['false_positive_rate']+.05)
        record={'epoch':epoch,'original_validation':current,'mixed_validation':mixed,'feasible':feasible}
        history.append(record)
        if feasible:
            rank=(mixed['f1'],current['fsd_val']['f1'],current['esc_val']['f1'])
            if best is None or rank>best['rank']:
                best={'rank':rank,'epoch':epoch,'state':copy.deepcopy(model.state_dict()),
                      'mixed':mixed,'original':current}
        print(f'epoch {epoch}: mixed {mixed["confusion"]} F1={mixed["f1"]:.3f} feasible={feasible}',flush=True)
    result={'seed':SEED,'sources':{'train_bark':len(train_bark),'train_household_noise':len(train_noise),
                                 'train_mixtures':len(mixed_train),'val_bark':len(val_bark),
                                 'val_household_noise':len(val_noise)},
            'mix_levels':[.2,.4,.8],'threshold':threshold,
            'baseline_validation':{'original':baseline_val,'mixed':baseline_mixed},
            'history':history,'selected_epoch':best['epoch'] if best else None,
            'scope':'weak clip-level Bark labels; mixed validation simulated; FSD eval previously inspected',
            'promoted':False,
            'promotion_reason':'Validation gains must also survive external source checks without unacceptable false positives'}
    if best:
        model.load_state_dict(best['state'])
        torch.save({**saved,'state_dict':model.state_dict(),
                    'training_source':'FSD official train Bark + household noise mixtures; ESC-trained warm start'},CANDIDATE)
        result['candidate_sha256']=hashlib.sha256(CANDIDATE.read_bytes()).hexdigest()
        result['candidate_validation']={'original':best['original'],'mixed':best['mixed']}
        # This post-selection set was previously inspected; no further tuning.
        audit=json.loads((ROOT/'model_results.json').read_text(encoding='utf-8'))
        check=AudioPredictor(CANDIDATE)
        eval_root=Path('artifacts/datasets/fsd50k/eval_subset')
        audit_rows=[]
        for case in audit['cases']:
            original=eval_root/(case['source_id']+'.wav')
            if hashlib.sha256(original.read_bytes()).hexdigest()!=case['sha256']:
                raise ValueError('audit source checksum changed')
            prediction=check.predict(original)
            audit_rows.append({'source_id':case['source_id'],'reference_bark':case['reference_bark'],
                               'baseline_score':case['score'],'candidate_score':prediction['dog_score'],
                               'candidate_detected':prediction['dog_score']>=threshold})
        result['inspected_eval_audit']={'positive_detected':sum(x['candidate_detected'] for x in audit_rows if x['reference_bark']),
                                        'positive_total':sum(x['reference_bark'] for x in audit_rows),
                                        'negative_false_positives':sum(x['candidate_detected'] for x in audit_rows if not x['reference_bark']),
                                        'negative_total':sum(not x['reference_bark'] for x in audit_rows),
                                        'rows':audit_rows}
        comparison={}
        for split in ('esc_test','fsd_eval'):
            bags=checked_features(rows[split])
            comparison[split]={name:group_metrics(candidate_model,bags,rows[split],mean,std,threshold)
                               for name,candidate_model in (('baseline',baseline),('candidate',model))}
        result['inspected_full_eval_comparison']=comparison
        result['simulated_mixture_audit']=[{'filename':p.name,
            'baseline_score':AudioPredictor(MODEL).predict(p)['dog_score'],
            'candidate_score':check.predict(p)['dog_score']}
            for p in sorted(ROOT.glob('bark_with_*.wav'))]
    ROOT.mkdir(exist_ok=True)
    (ROOT/'training_comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'baseline_mixed':baseline_mixed,'best_epoch':result['selected_epoch'],
                      'candidate_validation':result.get('candidate_validation'),
                      'inspected_eval_audit':{k:v for k,v in result.get('inspected_eval_audit',{}).items() if k!='rows'}},
                     ensure_ascii=False),flush=True)


if __name__=='__main__':main()
