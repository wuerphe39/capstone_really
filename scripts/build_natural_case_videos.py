"""Attach each real demo sound to its own recorded upload/RAG walkthrough."""
import json
import subprocess
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'artifacts' / 'ai_sound_demo_20261012' / 'natural'
FONT = 'C:/Windows/Fonts/malgun.ttf'
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
TITLES = {'detected': '사례 1 · 개 짖음 후보 감지',
          'missed': '사례 2 · 말소리 속 짖음 놓침',
          'speech_only': '사례 3 · 생성 말소리만'}
REVIEW = {'pet_vocalization': '반려견 소리', 'uncertain': '판단하기 어려움', 'other': '기타 소리'}


def ffmpeg(*args):
    subprocess.run([FFMPEG, '-hide_banner', '-loglevel', 'error', '-y', *map(str, args)], check=True)


def card(path, title, lines):
    image = Image.new('RGB', (1280, 720), '#f7f8fc')
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((40, 40, 1240, 680), radius=24, fill='white', outline='#dbe1ef', width=2)
    draw.rounded_rectangle((80, 82, 490, 130), radius=14, fill='#eeedff')
    draw.text((101, 91), 'PetMind · 공개·생성 음원 시연', font=ImageFont.truetype(FONT, 22), fill='#524ee3')
    draw.text((83, 175), title, font=ImageFont.truetype(FONT, 47), fill='#21263a')
    for i, line in enumerate(lines):
        draw.text((88, 275 + i*72), line, font=ImageFont.truetype(FONT, 29), fill='#424b61')
    draw.text((88, 615), '실제 가정 녹음·독립 정확도 검증이 아닙니다.',
              font=ImageFont.truetype(FONT, 22), fill='#777e94')
    image.save(path)


def still(name, heading, lines, seconds, audio=None):
    picture = FOLDER / f'{name}.png'
    segment = FOLDER / f'{name}.mp4'
    card(picture, heading, lines)
    source = ['-i', FOLDER / audio] if audio else ['-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=48000']
    ffmpeg('-loop', '1', '-framerate', '25', '-i', picture, *source, '-t', seconds,
           '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-r', '25',
           '-c:a', 'aac', '-ar', '48000', '-ac', '2', segment)
    return segment


def build(index, result):
    name = result['case']
    score = result['model_score']
    claims = {c['id']: c for c in result['rag']['claims']}
    if result['rag']['failure'] or 'current.audio_lstm' not in claims:
        raise ValueError(f'Grounded model evidence missing for {name}')
    steps = result['rag'].get('next_steps') or []
    if not steps or result['observation_id'] not in steps[0]['observation_ids']:
        raise ValueError(f'Evidence-linked guidance missing for {name}')
    care = result.get('care') or {}
    if care.get('current_audio', {}).get('observation_id') != result['observation_id']:
        raise ValueError(f'Current-observation care evidence missing for {name}')
    first = still(f'{index}_{name}_opening', TITLES[name], [
        '지금 들리는 5초 음원을 실제 웹 UI에 업로드합니다.',
        '사람 말소리: Gemini 3.8 TTS · 짖음: FSD50K #15791',
        f'실험 후보 LSTM 점수 {score:.3f} / 기준 0.900'], 5, result['input'])
    ui = FOLDER / f'{index}_{name}_ui_with_silence.mp4'
    ffmpeg('-i', FOLDER / f'{index}_{name}_ui.webm',
           '-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=48000',
           '-shortest', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-r', '25',
           '-c:a', 'aac', '-ar', '48000', '-ac', '2', ui)
    found = '1개' if result['detected'] else '0개'
    care_provider = 'Gemini Lite' if care['provider'].startswith('gemini:') else '기본 판단(대체 동작)'
    care_summary = care['summary']
    last = still(f'{index}_{name}_closing', 'RAG 근거와 케어 확인', [
        f"LSTM 후보 1개 중 {found} · 확인 의견: {REVIEW[result['review']['label']]}",
        f"케어 제공자: {care_provider} · 현재 관찰 #{result['observation_id']} 반영",
        care_summary[:35],
        care_summary[35:70] + ('…' if len(care_summary) > 70 else '')], 10)
    listing = FOLDER / f'{index}_{name}_parts.txt'
    listing.write_text(''.join(f"file '{piece.as_posix()}'\n" for piece in (first, ui, last)), encoding='utf-8')
    destination = FOLDER / f'PetMind_case_{index}_{name}.mp4'
    ffmpeg('-f', 'concat', '-safe', '0', '-i', listing, '-c', 'copy', '-movflags', '+faststart', destination)
    return destination


def main():
    data = json.loads((FOLDER / 'ui_case_results.json').read_text(encoding='utf-8'))
    if len(data) != 3 or any(row.get('error') for row in data):
        raise ValueError('All three web UI cases must succeed before packaging')
    for index, row in enumerate(data, 1):
        print(build(index, row))


if __name__ == '__main__':
    main()
