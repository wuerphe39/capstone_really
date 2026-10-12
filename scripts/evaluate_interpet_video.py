"""Actual held-out dog videos through existing detector/tracker/LSTM, no fake labels."""
import argparse
import hashlib
import json
from pathlib import Path

from scripts.prepare_interpet import ROOT, fetch
from pet_monitor.video import analyze_video


def run(candidate):
    manifest = json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'))
    dogs = sorted(dog for dog, split in manifest['dog_assignments'].items() if split == 'test')
    captions = json.loads((ROOT/'video_caption/captions.json').read_text(encoding='utf-8'))
    output = Path('artifacts/interpet_evaluation/videos'); output.mkdir(parents=True, exist_ok=True)
    rows = []
    for dog in dogs:
        item = next(row for row in manifest['files'] if row['dog'] == dog and row['windows'] > 0)
        clip = item['clip']
        video = fetch(f'video/interpet_{clip}/sync_ego_cam.mp4', manifest['revision'])
        reports = {}
        for name, checkpoint in [('v2', Path('artifacts/lstm/trajectory_lstm.pt')), ('v3', candidate)]:
            result = analyze_video(video, checkpoint, output/f'{clip}_{name}')
            after = [row for row in result['predictions'] if row['t'] >= 9.8]
            result['post_warmup_coverage'] = sum(row['label'] != 'unknown' for row in after)/len(after) if after else None
            diagnostics = result['tracking_diagnostics']
            result['tracking_counts'] = {'sampled_frames': len(diagnostics),
                'dog_detected_frames': sum(row['dog_detections'] > 0 for row in diagnostics),
                'any_track_frames': sum(bool(row['visible_track_ids']) for row in diagnostics),
                'selected_track_frames': sum(row['selected_track_matched'] for row in diagnostics),
                'other_id_only_frames': sum(bool(row['visible_track_ids']) and not row['selected_track_matched'] for row in diagnostics)}
            path = output/f'{clip}_{name}.json'; path.write_text(json.dumps(result, indent=2), encoding='utf-8')
            reports[name] = {key: result[key] for key in ['duration_s', 'source_fps', 'tracked_samples',
                                                        'seconds_by_label', 'post_warmup_coverage', 'training_source']}
            reports[name]['tracking_counts'] = result['tracking_counts']
        caption = captions.get('interpet_'+clip, {})
        rows.append({'clip': clip, 'dog': dog, 'split': 'test', 'video_sha256': hashlib.sha256(video.read_bytes()).hexdigest(),
                     'caption': caption.get('caption'), 'caption_duration_s': caption.get('duration_seconds'),
                     'reports': reports, 'behavior_accuracy': None})
        print(json.dumps(rows[-1], ensure_ascii=True), flush=True)
    report = {'dataset': 'InterPet4D', 'revision': manifest['revision'], 'records': rows,
              'selection': 'first quality-qualified clip per held-out dog, before viewing model outputs',
              'limits': ['clip captions have no action timestamps', 'coverage is not behavior accuracy',
                         'ego camera moves with human', 'world pose pretraining differs from image box trajectory']}
    (output/'evaluation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--candidate', type=Path, required=True)
    run(parser.parse_args().candidate)
