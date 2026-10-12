import hashlib
import io
import json

import numpy as np
import pytest
import soundfile as sf

from scripts import prepare_demo_audio


def test_demo_audio_requires_matching_official_metadata_and_hash(tmp_path, monkeypatch):
    source = tmp_path/'source'
    source.mkdir()
    content = io.BytesIO()
    sf.write(content, np.zeros(220500, dtype=np.float32), 44100, format='WAV')
    name = '5-example-A-0.wav'
    (source/name).write_bytes(content.getvalue())
    (tmp_path/'esc50.csv').write_text('filename,category,fold,esc10,src_file\n'
        f'{name},dog,5,True,example\n', encoding='utf-8')
    (tmp_path/'LICENSE').write_text(
        '- [5-example-A.ogg]: clip derived from Example.wav (http://freesound.org/example) by Example Author [CC0]',
        encoding='utf-8')
    digest = hashlib.sha256(content.getvalue()).hexdigest()
    monkeypatch.setattr(prepare_demo_audio, 'SAMPLES', {name: ('dog', 5, digest)})

    output = tmp_path/'demo'
    result = prepare_demo_audio.prepare(output, source)
    assert result['records'][0]['sha256'] == digest
    assert result['records'][0]['license'] == 'CC BY'
    assert result['records'][0]['fold'] == 5
    assert result['records'][0]['original_author'] == 'Example Author'
    assert result['records'][0]['original_source_url'] == 'http://freesound.org/example'
    assert result['records'][0]['original_license'] == 'CC0'
    assert (output/'audio'/name).read_bytes() == content.getvalue()
    assert json.loads((output/'demo_manifest.json').read_text(encoding='utf-8')) == result

    (tmp_path/'esc50.csv').write_text('filename,category,fold,esc10,src_file\n'
        f'{name},rain,5,True,example\n', encoding='utf-8')
    with pytest.raises(ValueError, match='metadata'):
        prepare_demo_audio.prepare(output, source)
    (tmp_path/'esc50.csv').write_text('filename,category,fold,esc10,src_file\n'
        f'{name},dog,5,True,example\n', encoding='utf-8')
    (output/'audio'/name).write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='hash changed'):
        prepare_demo_audio.prepare(output, source)
    (output/'audio'/name).write_bytes(content.getvalue())
    (tmp_path/'LICENSE').write_text('missing attribution', encoding='utf-8')
    with pytest.raises(ValueError, match='attribution missing'):
        prepare_demo_audio.prepare(output, source)


def test_demo_audio_preserves_official_fold_one(tmp_path, monkeypatch):
    source = tmp_path/'source'
    source.mkdir()
    content = io.BytesIO()
    sf.write(content, np.zeros(220500, dtype=np.float32), 44100, format='WAV')
    name = '1-example-A-0.wav'
    (source/name).write_bytes(content.getvalue())
    (tmp_path/'esc50.csv').write_text('filename,category,fold,esc10,src_file\n'
        f'{name},dog,1,True,example\n', encoding='utf-8')
    (tmp_path/'LICENSE').write_text(
        '- [1-example-A.ogg]: clip derived from Example.wav (http://freesound.org/example) by Author [CC0]',
        encoding='utf-8')
    digest = hashlib.sha256(content.getvalue()).hexdigest()
    monkeypatch.setattr(prepare_demo_audio, 'SAMPLES', {name: ('dog', 1, digest)})

    result = prepare_demo_audio.prepare(tmp_path/'demo', source)
    assert result['records'][0]['fold'] == 1
