import json
import argparse
from pathlib import Path

from pet_monitor.video import analyze_video
from pet_monitor.temporal_candidates import diagnostics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--filename', default='davis_dog_replay_5fps.mp4')
    parser.add_argument('--report', default='artifacts/video_analysis.json')
    args = parser.parse_args()
    folder = Path('artifacts/media')
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    source = next((item for item in manifest if item['type'] == 'video' and item['filename'] == args.filename), None)
    if source is None:
        raise SystemExit('Prepared video missing; run python -m scripts.prepare_davis first')
    result = analyze_video(folder / source['filename'])
    result['source'] = source
    result['quality_diagnostics'] = diagnostics(result)
    Path(args.report).write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in result.items() if key not in {'points', 'predictions', 'source'}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
