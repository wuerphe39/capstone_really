"""Extract publisher annotations only for the selected A2D dog clips.

The original annotations and images remain in ignored artifacts; no media is
redistributed. All archive member paths are matched against publisher IDs.
"""
import json
import re
import shutil
import tarfile
from collections import Counter

from scripts.prepare_a2d import ARCHIVE, ROOT, sha256


def run():
    manifest_path = ROOT / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if sha256(ARCHIVE) != manifest['archive_sha256']:
        raise ValueError('A2D archive differs from clip manifest')
    wanted = {row['id'] for row in manifest['records']}
    root = ROOT / 'annotations'
    pattern = re.compile(r'Release/Annotations/mat/([A-Za-z0-9_-]{11})/(\d{5})\.mat')
    seen = set()
    count = Counter()
    with tarfile.open(ARCHIVE, 'r:bz2') as source:
        for member in source:
            match = pattern.fullmatch(member.name)
            if not match or match.group(1) not in wanted:
                continue
            clip_id, frame = match.groups()
            key = (clip_id, frame)
            if key in seen or not member.isfile():
                raise ValueError('duplicate or invalid annotation archive member')
            stream = source.extractfile(member)
            if stream is None:
                raise ValueError('annotation unreadable')
            target = root / clip_id / f'{frame}.mat'
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('wb') as output:
                shutil.copyfileobj(stream, output)
            if target.stat().st_size != member.size:
                raise ValueError('annotation size mismatch')
            count[clip_id] += 1
            seen.add(key)
    print(json.dumps({'clips_with_annotations': len(count), 'annotation_files': len(seen),
                      'missing_selected_clips': sorted(wanted-set(count)),
                      'counts': dict(Counter(count.values()))}), flush=True)


if __name__ == '__main__':
    run()
