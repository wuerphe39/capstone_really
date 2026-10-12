"""Create a browser-compatible derivative, preserving timing and provenance.

Optional local dependency: pip install imageio-ffmpeg==0.6.0
Re-run scripts.evaluate_video on the NEW filename; never relabel a cached report.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def main():
    import imageio_ffmpeg
    parser = argparse.ArgumentParser()
    parser.add_argument('--filename', default='davis_dog_replay_5fps.mp4')
    args = parser.parse_args()
    folder = Path('artifacts/media').resolve()
    manifest = folder/'manifest.json'
    entries = json.loads(manifest.read_text(encoding='utf-8'))
    source = next(e for e in entries if e['filename'] == args.filename and e['type'] == 'video')
    original = (folder/source['filename']).resolve()
    if not original.is_relative_to(folder) or not original.is_file():
        raise ValueError('prepared video missing')
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    if digest != source['sha256']:
        raise ValueError('source checksum mismatch')
    target = original.with_name(original.stem+'_h264.mp4')
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-hide_banner', '-loglevel', 'error',
                    '-i', str(original), '-c:v', 'libx264', '-crf', '18', '-pix_fmt', 'yuv420p',
                    '-movflags', '+faststart', '-an', '-y', str(target)], check=True)
    derivative = {**source, 'filename': target.name, 'parent_sha256': digest,
                  'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                  'transformation': source.get('transformation', '')+'; H.264 browser derivative, source timing preserved'}
    entries = [e for e in entries if e['filename'] != target.name]+[derivative]
    manifest.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding='utf-8')
    print(target.name)


if __name__ == '__main__':
    main()
