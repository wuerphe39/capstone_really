import numpy as np
import pytest
import soundfile as sf

from petmind import music


def song(path, seconds, freq=440.0, rate=22050):
    t = np.arange(int(seconds * rate)) / rate
    sf.write(path, (0.5 * np.sin(2 * np.pi * freq * t)).astype(np.float32), rate)
    return path


def test_generated_piano_is_quiet_and_has_the_asked_length(tmp_path):
    path = music.music_file(tmp_path, 'calm_piano', 8)
    data, rate = sf.read(path)
    assert abs(len(data) / rate - 8) < 0.1
    assert 0.05 < np.abs(data).max() <= 0.31  # soft: well below full scale
    assert abs(data[0]) < 0.01 and abs(data[-1]) < 0.01  # fades in and out
    assert music.music_file(tmp_path, 'calm_piano', 8) == path  # generated once, then reused


def test_a_style_without_a_generator_needs_a_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        music.music_file(tmp_path, 'nature_sounds')


def test_the_guardians_songs_are_played_in_turn_and_start_over(tmp_path):
    (tmp_path / 'calm_piano').mkdir()
    song(tmp_path / 'calm_piano' / 'a.flac', 12, 220)
    song(tmp_path / 'calm_piano' / 'b.flac', 12, 330)
    first, second, third = (music.music_file(tmp_path, 'calm_piano', 10) for _ in range(3))
    assert first.name.startswith('a_') and second.name.startswith('b_') and third.name.startswith('a_')
    assert third == first  # converted once, then reused


def test_a_long_song_is_cut_and_every_song_ends_softly(tmp_path):
    (tmp_path / 'calm_piano').mkdir()
    song(tmp_path / 'calm_piano' / 'long.flac', 30)
    data, rate = sf.read(music.music_file(tmp_path, 'calm_piano', 10))
    assert abs(len(data) / rate - 10) < 0.1
    assert abs(data[0]).max() < 0.01 and abs(data[-1]).max() < 0.01          # fades in and out
    assert np.abs(data[: rate]).max() < np.abs(data[3 * rate: 5 * rate]).max()  # the first second is still fading in
    assert np.abs(data[-rate:]).max() < np.abs(data[3 * rate: 5 * rate]).max() * 0.4  # the last second is nearly gone


def test_a_song_shorter_than_the_limit_still_fades_out(tmp_path):
    (tmp_path / 'calm_piano').mkdir()
    song(tmp_path / 'calm_piano' / 'short.flac', 5)
    data, rate = sf.read(music.music_file(tmp_path, 'calm_piano', 60))
    assert 4.5 < len(data) / rate < 5.5 and abs(data[-1]).max() < 0.01


def test_a_single_wav_in_the_music_folder_is_still_used(tmp_path):
    song(tmp_path / 'calm_piano.wav', 12)
    assert music.music_file(tmp_path, 'calm_piano', 10).name.startswith('calm_piano_')


def test_reggae_and_soft_rock_alternate(tmp_path):
    for folder, names in (('reggae', ('r1', 'r2')), ('soft_rock', ('s1', 's2', 's3'))):
        (tmp_path / folder).mkdir()
        for name in names:
            song(tmp_path / folder / f'{name}.flac', 12)
    played = [music.music_file(tmp_path, 'calm_piano', 10).name.split('_')[0] for _ in range(6)]
    assert played == ['r1', 's1', 'r2', 's2', 's3', 'r1']  # genres alternate; the longer list finishes, then it starts over


def test_a_lower_target_makes_a_quieter_file_and_the_default_is_quieter_than_before(tmp_path, monkeypatch):
    (tmp_path / 'reggae').mkdir()
    song(tmp_path / 'reggae' / 's.flac', 20)
    rms = lambda path: float(np.sqrt(np.mean(sf.read(path)[0] ** 2)))
    loud = music.music_file(tmp_path, 'calm_piano', 10, lufs=-28)
    quiet = music.music_file(tmp_path, 'calm_piano', 10, lufs=-40)
    assert loud != quiet and rms(quiet) < rms(loud) * 0.4  # 12 dB is a quarter of the amplitude
    monkeypatch.delenv('PETMIND_MUSIC_LUFS', raising=False)
    assert music.target_lufs() == -34.0
    monkeypatch.setenv('PETMIND_MUSIC_LUFS', '-42')
    assert music.target_lufs() == -42.0
    monkeypatch.setenv('PETMIND_MUSIC_LUFS', 'loud')
    assert music.target_lufs() == -34.0   # a bad value falls back instead of failing during a demo
    monkeypatch.setenv('PETMIND_MUSIC_LUFS', '0')
    assert music.target_lufs() == -14.0   # and a silly value is clamped
