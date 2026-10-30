"""Music for the speaker agent (petmind/device_agent.py --play).

Real songs are the guardian's own files: put WAV/MP3/FLAC/M4A/OGG files in artifacts/music/reggae/ and artifacts/music/soft_rock/
(a calm_piano/ folder also counts). Those two genres gave the best stress signs in a kennel study (Bowman et al. 2017). The
agent plays the songs in turn, one per approval, alternating the genres, because dogs get used to a single piece
(Bowman et al. 2017 suggest varying the music). Every file is first converted to a quiet WAV of at most `seconds` with a
slow fade-out: stopping music abruptly was followed by more barking in that study. Without any file, a quiet piece is
generated locally as a placeholder (no recording, no licence question): slow soft plucked notes for calm_piano, soft
filtered noise for white_noise. Nothing here is proven to calm a particular dog; it is only played after the guardian approves.
"""
import json
import os
import subprocess
from pathlib import Path

import imageio_ffmpeg
import numpy as np
import soundfile as sf

SAMPLE_RATE = 22050
GENERATED = ('calm_piano', 'white_noise')
AUDIO_SUFFIXES = {'.wav', '.mp3', '.flac', '.m4a', '.ogg'}
FADE_IN_S, FADE_OUT_S = 2, 8
DEFAULT_LUFS = -40.0  # 12 dB (a quarter of the amplitude) below the first version (-28), which was louder than expected; chosen by ear


def target_lufs():
    """Loudness the songs are brought to. Lower (e.g. -40) is quieter; set PETMIND_MUSIC_LUFS to change it. The PC volume still applies."""
    try:
        value = float(os.getenv('PETMIND_MUSIC_LUFS', DEFAULT_LUFS))
    except ValueError:
        return DEFAULT_LUFS
    return min(max(value, -50.0), -14.0)


def _fade(signal, seconds):
    n = int(seconds * SAMPLE_RATE)
    envelope = np.ones(len(signal))
    envelope[:n] = np.linspace(0, 1, n)
    envelope[-n:] = np.linspace(1, 0, n)
    return signal * envelope


def calm_piano(seconds):
    rng = np.random.default_rng(7)  # fixed: the same piece every time
    scale = np.array([261.63, 293.66, 329.63, 392.00, 440.00, 523.25])  # C major pentatonic
    out = np.zeros(int(seconds * SAMPLE_RATE))
    t_note = np.arange(int(4.0 * SAMPLE_RATE)) / SAMPLE_RATE
    position, beat = 0.0, 0
    while position < seconds - 1:
        freq = scale[rng.integers(len(scale))] * (0.5 if beat % 4 == 0 else 1.0)
        tone = sum(amp * np.sin(2 * np.pi * freq * k * t_note) * np.exp(-t_note * (1.6 + 1.4 * k))
                   for k, amp in ((1, 1.0), (2, 0.35), (3, 0.15), (4, 0.06)))
        tone *= np.minimum(t_note / 0.012, 1.0)  # soft attack
        start = int(position * SAMPLE_RATE)
        end = min(start + len(tone), len(out))
        out[start:end] += tone[:end - start] * rng.uniform(0.7, 1.0)
        position += rng.choice([1.5, 1.5, 2.0, 3.0])
        beat += 1
    return _fade(out / np.abs(out).max() * 0.30, 3.0)


def white_noise(seconds):
    rng = np.random.default_rng(11)
    noise = rng.standard_normal(int(seconds * SAMPLE_RATE))
    smooth = np.convolve(noise, np.ones(8) / 8, mode='same')  # soften the hiss
    return _fade(smooth / np.abs(smooth).max() * 0.18, 3.0)


# Folders that make up a style's playlist, in the order they alternate. calm_piano is the style the care suggestion asks for.
PLAYLISTS = {'calm_piano': ('reggae', 'soft_rock', 'calm_piano')}


def songs_in(folder):
    folder = Path(folder)
    return sorted(f for f in folder.iterdir() if f.suffix.lower() in AUDIO_SUFFIXES) if folder.is_dir() else []


def own_files(music_dir, style):
    """The guardian's songs for `style`, alternating between its genre folders (first of each, then second of each, ...)."""
    lists = [songs_in(Path(music_dir) / name) for name in PLAYLISTS.get(style, (style,))]
    single = Path(music_dir) / f'{style}.wav'
    mixed = [song for round_ in range(max(map(len, lists), default=0)) for songs in lists for song in songs[round_:round_ + 1]]
    return mixed + ([single] if single.is_file() else [])


def next_index(music_dir, style, count):
    """Round-robin position for `style`, remembered between runs so every approval gets the next song."""
    state_path = Path(music_dir) / '.rotation.json'
    try:
        state = json.loads(state_path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        state = {}
    position = int(state.get(style, 0)) % count
    state[style] = position + 1
    state_path.write_text(json.dumps(state), encoding='utf-8')
    return position


def prepared(source, music_dir, seconds, lufs=None):
    """A quiet WAV of at most `seconds` made from `source`, fading in and slowly out. Cached next to the music."""
    cache = Path(music_dir) / '_cache'
    cache.mkdir(parents=True, exist_ok=True)
    lufs = target_lufs() if lufs is None else lufs
    out = cache / f'{source.stem}_{int(seconds)}s_{int(lufs)}lu_{int(source.stat().st_mtime)}.wav'  # a new level makes a new file
    if not out.is_file():
        raw = out.with_suffix('.raw.wav')
        # loudnorm to a low level so the songs have similar loudness; the PC volume still decides how loud it really is
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-hide_banner', '-loglevel', 'error', '-y', '-i', str(source), '-t', str(seconds),
                        '-af', f'loudnorm=I={lufs:g}:TP=-4', '-ar', '44100', '-ac', '2', '-c:a', 'pcm_s16le', str(raw)], check=True)
        data, rate = sf.read(raw, dtype='float32')
        raw.unlink()
        # The fades follow the real length: a song shorter than `seconds` must still end softly.
        envelope = np.ones(len(data), dtype=np.float32)
        fade_in, fade_out = min(int(FADE_IN_S * rate), len(data) // 2), min(int(FADE_OUT_S * rate), len(data) // 2)
        envelope[:fade_in] = np.linspace(0, 1, fade_in, dtype=np.float32)
        envelope[len(data) - fade_out:] = np.minimum(envelope[len(data) - fade_out:], np.linspace(1, 0, fade_out, dtype=np.float32))
        sf.write(out, data * envelope[:, None], rate, subtype='PCM_16')
    return out


def music_file(music_dir, style, seconds=60, lufs=None):
    """Path of a WAV to play for `style`: the guardian's own songs in turn, else a generated quiet piece."""
    music_dir = Path(music_dir)
    music_dir.mkdir(parents=True, exist_ok=True)
    files = own_files(music_dir, style)
    if files:
        return prepared(files[next_index(music_dir, style, len(files))], music_dir, seconds, lufs)
    if style not in GENERATED:
        raise FileNotFoundError(f'no music for {style}: put files in {music_dir / style} (this style is not generated)')
    path = music_dir / f'generated_{style}_{int(seconds)}s.wav'
    if not path.is_file():
        signal = calm_piano(seconds) if style == 'calm_piano' else white_noise(seconds)
        sf.write(path, signal.astype(np.float32), SAMPLE_RATE, subtype='PCM_16')
    return path
