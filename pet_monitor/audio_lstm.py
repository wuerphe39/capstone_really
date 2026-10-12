"""Audio-only experimental classifier, separate from the trajectory checkpoint."""
from math import gcd
import io

import numpy as np
import soundfile as sf
import torch
from scipy.signal import resample_poly
from torch import nn

RATE = 16000
N_MELS = 40


def logmel(path):
    signal, rate = sf.read(path, dtype='float32', always_2d=True)
    if not len(signal) or len(signal)/rate > 30 or not np.isfinite(signal).all():
        raise ValueError('expected finite nonempty audio up to 30 seconds')
    signal = signal.mean(1)
    divisor = gcd(rate, RATE)
    signal = resample_poly(signal, RATE//divisor, rate//divisor).astype(np.float32)
    # Fixed 5-second input contract; no time stretching.
    signal = np.pad(signal[:RATE*5], (0, max(0, RATE*5-len(signal))))
    power = torch.stft(torch.from_numpy(signal), n_fft=512, hop_length=320,
                       win_length=400, window=torch.hann_window(400), return_complex=True).abs().square()
    mel = lambda hz: 2595*np.log10(1+hz/700)
    hz = 700*(10**(np.linspace(mel(0), mel(RATE/2), N_MELS+2)/2595)-1)
    bins = np.linspace(0, RATE/2, 257)
    bank = np.array([np.maximum(0, np.minimum((bins-a)/(b-a), (c-bins)/(c-b)))
                     for a,b,c in zip(hz, hz[1:], hz[2:])], dtype=np.float32)
    return torch.log(torch.from_numpy(bank)@power+1e-6).T.contiguous()


class AudioClassifier(nn.Module):
    def __init__(self, kind='lstm'):
        super().__init__()
        if kind not in {'lstm', 'pooled'}:
            raise ValueError('unknown classifier')
        self.kind = kind
        self.encoder = nn.LSTM(N_MELS, 32, batch_first=True) if kind == 'lstm' else None
        self.head = nn.Linear(32 if kind == 'lstm' else N_MELS*2, 2)

    def forward(self, x):
        if self.encoder is not None:
            sequence, _ = self.encoder(x)
            features = sequence.mean(1)
        else:
            features = torch.cat([x.mean(1), x.std(1)], dim=1)
        return self.head(features)


class AudioPredictor:
    """Experimental clip classification; score is not calibrated probability."""
    def __init__(self, checkpoint):
        saved = torch.load(checkpoint, map_location='cpu', weights_only=True)
        if saved['labels'] != ['other','dog'] or saved['sample_rate'] != RATE or saved['window_s'] != 5:
            raise ValueError('incompatible audio checkpoint')
        self.model = AudioClassifier(saved['kind'])
        self.model.load_state_dict(saved['state_dict']); self.model.eval()
        self.mean, self.std, self.threshold = saved['mean'], saved['std'], saved['threshold']

    def predict(self, path):
        values, rate = sf.read(path,dtype='float32',always_2d=True)
        if not len(values) or len(values)/rate > 30:
            raise ValueError('expected audio up to 30 seconds')
        windows = []
        for start in range(0,len(values),rate*5):
            chunk = values[start:start+rate*5]
            buffer = io.BytesIO(); sf.write(buffer,chunk,rate,format='WAV',subtype='FLOAT'); buffer.seek(0)
            features = (logmel(buffer)-self.mean)/self.std
            with torch.inference_mode():
                score = float(self.model(features[None]).softmax(-1)[0,1])
            windows.append({'start_s':start/rate,'end_s':(start+len(chunk))/rate,
                'dog_score':score,'label':'dog_candidate' if score >= self.threshold else 'other_candidate',
                'padded':len(chunk)<rate*5})
        return {'windows':windows,'dog_score':max(w['dog_score'] for w in windows),
                'threshold':self.threshold,'scope':'experimental Dog clip classifier; uncalibrated score; not emotion or sound-source identity'}


def binary_metrics(expected, probabilities, threshold=.5):
    expected = np.asarray(expected, dtype=bool)
    predicted = np.asarray(probabilities) >= threshold
    tp = int((predicted & expected).sum()); fp = int((predicted & ~expected).sum())
    fn = int((~predicted & expected).sum()); tn = int((~predicted & ~expected).sum())
    return {'samples': len(expected), 'dog_support': int(expected.sum()),
            'precision': tp/(tp+fp) if tp+fp else 0,
            'recall': tp/(tp+fn) if tp+fn else None,
            'f1': 2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0,
            'false_positive_rate': fp/(fp+tn) if fp+tn else None,
            'confusion': {'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn}, 'threshold': float(threshold)}
