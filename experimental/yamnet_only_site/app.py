"""Local-only WAV comparison site using the frozen YAMNet Bark score.

Run with the separate TensorFlow environment documented in README.md. This
does not write observations, change the PetMind API, or train a model.
"""

import argparse
import io
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from math import gcd
from pathlib import Path

os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '2')

import numpy as np
import soundfile as sf
import tensorflow as tf
import tensorflow_hub as hub
from scipy.signal import resample_poly


INDEX = Path(__file__).with_name('index.html')
MODEL_HANDLE = 'https://tfhub.dev/google/yamnet/1'
RATE = 16_000
WINDOW_S = 5
MAX_SECONDS = 30
MAX_BYTES = 12 * 1024 * 1024
# Selected on the FSD50K/ESC validation split; never tuned on user uploads.
BARK_THRESHOLD = 0.05


def analyze_wav(content: bytes, model, bark_index: int) -> dict:
    if not content or len(content) > MAX_BYTES:
        raise ValueError('12MB 이하 WAV 파일을 선택해 주세요.')
    try:
        info = sf.info(io.BytesIO(content))
        if info.format != 'WAV' or not 0 < info.duration <= MAX_SECONDS or info.channels > 2:
            raise ValueError('30초 이하 모노/스테레오 WAV 파일이 필요합니다.')
        samples, sample_rate = sf.read(io.BytesIO(content), dtype='float32', always_2d=True)
    except (RuntimeError, sf.LibsndfileError) as exc:
        raise ValueError('WAV 파일을 읽을 수 없습니다.') from exc
    if not len(samples) or not np.isfinite(samples).all() or np.max(np.abs(samples)) > 1:
        raise ValueError('정상적인 음성 샘플이 아닙니다.')
    signal = samples.mean(axis=1)
    if sample_rate != RATE:
        factor = gcd(sample_rate, RATE)
        signal = resample_poly(signal, RATE // factor, sample_rate // factor).astype(np.float32)
    windows = []
    for start in range(0, len(signal), RATE * WINDOW_S):
        chunk = signal[start:start + RATE * WINDOW_S]
        actual_end = min((start + RATE * WINDOW_S) / RATE, info.duration)
        padded = len(chunk) < RATE * WINDOW_S
        if padded:
            chunk = np.pad(chunk, (0, RATE * WINDOW_S - len(chunk)))
        scores, _, _ = model(tf.convert_to_tensor(chunk, tf.float32))
        patch_scores = scores[:, bark_index].numpy()
        score = float(np.max(patch_scores))
        windows.append({
            'start_s': start / RATE,
            'end_s': round(actual_end, 3),
            'bark_score': round(score, 6),
            'candidate': score >= BARK_THRESHOLD,
            'padded': padded,
            'patch_count': len(patch_scores),
        })
    return {
        'model': 'YAMNet Bark (direct score; no LSTM)',
        'threshold': BARK_THRESHOLD,
        'duration_s': round(info.duration, 3),
        'original_sample_rate': sample_rate,
        'analyzed_windows': len(windows),
        'candidate_windows': sum(row['candidate'] for row in windows),
        'windows': windows,
        'note': '점수는 보정된 확률이나 실제 짖음 횟수가 아닙니다. 5초 창은 정확한 발생 시각이 아닙니다.',
    }


def make_handler(model, bark_index):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path not in ('/', '/health'):
                self.send_error(404)
                return
            if self.path == '/health':
                self.respond(200, json.dumps({'status': 'ready', 'model': 'YAMNet Bark'}).encode(), 'application/json')
            else:
                self.respond(200, INDEX.read_bytes(), 'text/html; charset=utf-8')

        def do_POST(self):
            if self.path != '/analyze':
                self.send_error(404)
                return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if self.headers.get('Content-Type', '').split(';', 1)[0] not in ('audio/wav', 'audio/x-wav'):
                    raise ValueError('WAV 파일만 분석할 수 있습니다.')
                if not 0 < size <= MAX_BYTES:
                    raise ValueError('12MB 이하 WAV 파일을 선택해 주세요.')
                result = analyze_wav(self.rfile.read(size), model, bark_index)
                self.respond(200, json.dumps(result, ensure_ascii=False).encode('utf-8'), 'application/json')
            except ValueError as exc:
                self.respond(422, json.dumps({'error': str(exc)}, ensure_ascii=False).encode('utf-8'), 'application/json')
            except Exception:
                self.respond(500, json.dumps({'error': '모델 분석에 실패했습니다.'}, ensure_ascii=False).encode('utf-8'), 'application/json')

        def respond(self, status, body, content_type):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(body)

    return Handler


def main():
    parser = argparse.ArgumentParser(description='Local YAMNet-only WAV test site')
    parser.add_argument('--port', type=int, default=8030)
    args = parser.parse_args()
    tf.config.threading.set_intra_op_parallelism_threads(2)
    model = hub.load(MODEL_HANDLE)
    from scripts.extract_yamnet_bark_features import class_indices
    bark_index = class_indices(model)[0]
    with ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(model, bark_index)) as server:
        print(f'YAMNet-only site: http://127.0.0.1:{args.port}/', flush=True)
        server.serve_forever()


if __name__ == '__main__':
    main()
