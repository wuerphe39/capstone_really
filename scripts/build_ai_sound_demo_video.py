"""Package the labeled five-second demo sounds and recorded web UI as one video."""
import json
import subprocess
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / 'artifacts' / 'ai_sound_demo_20261012'
FONT = 'C:/Windows/Fonts/malgun.ttf'
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def run(*args):
    subprocess.run([FFMPEG, '-hide_banner', '-loglevel', 'error', '-y', *map(str, args)], check=True)


def card(name, heading, lines):
    canvas = Image.new('RGB', (1280, 720), '#f7f8fc')
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((42, 42, 1238, 678), 24, fill='white', outline='#dbe1ef', width=2)
    draw.rounded_rectangle((80, 83, 410, 128), 14, fill='#eeedff')
    draw.text((102, 90), 'PetMind · 임시 시연', fill='#524ee3', font=ImageFont.truetype(FONT, 22))
    draw.text((86, 180), heading, fill='#21263a', font=ImageFont.truetype(FONT, 48))
    for index, line in enumerate(lines):
        draw.text((90, 280 + 68 * index), line, fill='#424b61', font=ImageFont.truetype(FONT, 30))
    draw.text((90, 610), '합성 시연 자료 · 실제 가정 성능이나 독립 정확도 검증이 아닙니다.',
              fill='#757e96', font=ImageFont.truetype(FONT, 21))
    output = DEMO / f'{name}.png'
    canvas.save(output)
    return output


def still_segment(name, heading, lines, seconds, audio=None):
    image = card(name, heading, lines)
    segment = DEMO / f'{name}.mp4'
    audio_args = ['-i', DEMO / audio] if audio else ['-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=48000']
    run('-loop', '1', '-framerate', '25', '-i', image, *audio_args, '-t', seconds,
        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-r', '25',
        '-c:a', 'aac', '-ar', '48000', '-ac', '2', segment)
    return segment


def main():
    results = json.loads((DEMO / 'ui_seed_results.json').read_text(encoding='utf-8'))
    scores = {row['filename']: row['score'] for row in results['records']}
    pieces = [still_segment('intro', 'AI 생성 말소리 + 공개 짖음 원본', [
        '소리 후보 → 보호자 확인 → 귀가 요약 → 기록 근거',
        '음성은 AI TTS, 짖음은 FSD50K #15791 원본입니다.',
        '아래 3개는 실제 집 안 녹음이 아닌 합성 시연입니다.'], 4)]
    cases = [
        ('case_detected', '사례 1 · 짖음 + 말소리', 'bark_tts_0.2.wav', '개 짖음 소리 후보 감지'),
        ('case_missed', '사례 2 · 짖음 + 더 큰 말소리', 'bark_tts_0.4.wav', '놓침 · 보호자 검토 필요'),
        ('case_negative', '사례 3 · 말소리만', 'tts_only.wav', '개 짖음 소리 후보 아님'),
    ]
    for name, heading, audio, finding in cases:
        pieces.append(still_segment(name, heading, [
            '지금 재생되는 소리가 분석에 사용된 5초 음원입니다.',
            f'실험 후보 LSTM 점수 {scores[audio]:.3f} / 판정 기준 0.900',
            finding], 5, audio))
    pieces.append(still_segment('ui_intro', '실제 웹 화면 조작', [
        '시연 전 API로 음원을 별도 DB에 등록했습니다.',
        '이어서 화면에서 사례 확인, 귀가 요약, RAG 근거를 봅니다.',
        '실험 후보 모델은 기본 모델로 배포하지 않았습니다.'], 4))
    ui = DEMO / 'ui_walkthrough_segment.mp4'
    source = DEMO / 'PetMind_AI_sound_interim_demo.mp4'
    run('-i', source, '-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=48000',
        '-shortest', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-r', '25',
        '-c:a', 'aac', '-ar', '48000', '-ac', '2', ui)
    pieces.append(ui)
    pieces.append(still_segment('outro', '결과와 남은 과제', [
        '3개 합성 사례 중 감지 1개, 놓침 1개, 비짖음 1개',
        '이 결과로 가정 환경의 감지 정확도를 주장하지 않습니다.',
        '실제 가정 녹음과 독립 검증이 다음 단계입니다.'], 5))
    concat = DEMO / 'video_segments.txt'
    concat.write_text(''.join(f"file '{path.as_posix()}'\n" for path in pieces), encoding='utf-8')
    final = DEMO / 'PetMind_AI_sound_presentation_demo.mp4'
    run('-f', 'concat', '-safe', '0', '-i', concat, '-c', 'copy', '-movflags', '+faststart', final)
    print(final)


if __name__ == '__main__':
    main()
