"""Build a clearly labeled presentation video from verified browser screenshots.

This is an edited walkthrough, not a continuous screen recording. Input screenshots
and model metrics are committed; public WAV and generated MP4 stay under artifacts/.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf
from PIL import Image, ImageDraw, ImageFont
from imageio_ffmpeg import get_ffmpeg_exe
from scipy.signal import resample_poly

from scripts.prepare_demo_audio import SAMPLES


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'artifacts/presentation_20261011'
IMAGES = ROOT/'docs/assets/ui'
FONT = Path(r'C:\Windows\Fonts\malgun.ttf')
BOLD = Path(r'C:\Windows\Fonts\malgunbd.ttf')
SIZE = (1920, 1080)
WHITE, INK, MUTED, BORDER, INDIGO = '#FAFAFA', '#0A0A0A', '#6B6B6B', '#E8E8EC', '#6366F1'


def font(size, bold=False):
    return ImageFont.truetype(str(BOLD if bold else FONT), size)


def draw_lines(draw, value, x, y, size=28, gap=49, color=INK):
    for line in value.split('\n'):
        draw.text((x, y), line, font=font(size), fill=color)
        y += gap


def slide(index, title, section, note, screenshot, footer, metrics=None):
    frame = Image.new('RGB', SIZE, WHITE)
    draw = ImageDraw.Draw(frame)
    draw.rectangle((0, 0, 1920, 8), fill=INDIGO)
    draw.text((68, 43), 'PetMind  /  CARE · EVIDENCE', font=font(26, True), fill=INDIGO)
    draw.text((68, 101), title, font=font(52, True), fill=INK)
    draw.text((70, 180), section, font=font(27), fill=MUTED)
    if screenshot:
        shot = Image.open(IMAGES/screenshot).convert('RGB')
        shot.thumbnail((1195, 695), Image.Resampling.LANCZOS)
        draw.rounded_rectangle((63, 253, 63 + shot.width + 22, 253 + shot.height + 22),
                               radius=12, fill='#FFFFFF', outline=BORDER, width=2)
        frame.paste(shot, (74, 264))
        x = 1320
    else:
        x = 90
    if metrics:
        draw.rounded_rectangle((90, 280, 1815, 740), radius=12, fill='#FFFFFF', outline=BORDER, width=2)
        labels = [('ESC-50 평가', metrics['esc_test']['baseline']['f1'],
                   metrics['esc_test']['augmented_mil']['f1']),
                  ('FSD50K 평가', metrics['fsd_eval']['baseline']['f1'],
                   metrics['fsd_eval']['augmented_mil']['f1'])]
        draw.text((130, 320), '같은 평가 자료 · F1', font=font(34, True), fill=INK)
        draw.text((870, 320), '기존 LSTM', font=font(30), fill=MUTED)
        draw.text((1290, 320), '증강·MIL 후보', font=font(30), fill=MUTED)
        for i, (label, old, new) in enumerate(labels):
            y = 410 + 120*i
            draw.text((130, y), label, font=font(34, True), fill=INK)
            draw.text((900, y), f'{old:.3f}', font=font(42, True), fill=INK)
            draw.text((1330, y), f'{new:.3f}', font=font(42, True), fill=INDIGO)
        draw_lines(draw, note, 100, 780, size=30, gap=52)
    else:
        draw_lines(draw, note, x, 302, size=28, gap=53)
    draw.line((68, 971, 1852, 971), fill=BORDER, width=2)
    draw.text((70, 992), footer, font=font(23), fill=MUTED)
    path = OUT/f'genesis_slide_{index:02d}.png'
    frame.save(path)
    return path


def speech(text, index, sample_rate):
    text_path = OUT/f'genesis_narration_{index:02d}.txt'
    wave_path = OUT/f'genesis_narration_{index:02d}.wav'
    text_path.write_text(text, encoding='utf-8')
    subprocess.run(['powershell', '-NoProfile', '-File', str(ROOT/'scripts/synthesize_walkthrough.ps1'),
                    '-TextPath', str(text_path), '-WavePath', str(wave_path)],
                   check=True, capture_output=True)
    values, rate = sf.read(wave_path, dtype='float32')
    if values.ndim == 2:
        values = values.mean(axis=1)
    if rate != sample_rate:
        from math import gcd
        factor = gcd(rate, sample_rate)
        values = resample_poly(values, sample_rate//factor, rate//factor)
    return values


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    data = json.loads((ROOT/'docs/evidence/audio_lstm_three_way.json').read_text(encoding='utf-8'))
    assert data['promoted'] is False
    metrics = data['evaluation']
    manifest = json.loads((ROOT/'artifacts/datasets/esc50_demo/demo_manifest.json').read_text(encoding='utf-8'))
    dog_source = next(row for row in manifest['records'] if row['filename'] == '5-203128-A-0.wav')
    dog_credit = (f"ESC-10 · 원본 {dog_source['original_author']} "
                  f"(Freesound #{dog_source['src_file']}, {dog_source['original_license']}) · 데이터셋 CC BY 3.0")
    browser_footer = '실제 로컬 브라우저 화면 · 별도 공개 시연 DB · 연속 클릭 녹화가 아닌 편집 영상'
    parts = [
      (18, '01  Genesis UI 적용', '기존 화면과 적용 후 화면 비교',
       '어두운 화면에서\n밝은 카드·명확한 수치·\n근거 링크 중심으로 정리.\n\n기능과 API는 유지.',
       'outing_before_after.png', '기존·변경 화면의 비교 캡처 · 실제 브라우저 연속 녹화 아님',
       '기존 다크 화면을 제네시스 스타일의 밝은 화면으로 바꾸었습니다. 관찰 수치와 근거 링크를 앞에 배치하고 기존 외출과 음원 기능은 유지했습니다.'),
      (18, '02  반려견의 하루를 근거로', '실제 브라우저 첫 화면',
       '외출 세션을 기준으로\n음원·관찰·귀가 설명을\n연결합니다.\n\n카메라 자동 촬영은 아님.',
       'verified_browser_dashboard_top.png', browser_footer,
       '펫마인드는 반려견의 감정이나 질환을 단정하지 않습니다. 외출 기록을 중심으로 관찰 신호와 보호자 의견, 원본 근거를 함께 보여줍니다.'),
      (26, '03  공개 음원 입력과 감지', 'ESC-50 Dog · 5초 분석 창',
       '모델 점수 93.9/100\n기준 90.0/100\n\n출처를 공개 시연으로 표시.\n업로드 뒤 파일·동의 초기화.\n이제 원본 5초를 재생합니다.',
       'verified_browser_second_upload_reset.png', dog_credit,
       '공개 이 에스 시 오십의 개 소리 자료를 입력했습니다. 오 초 분석 창의 모델 점수는 구십삼 점 구입니다. 이는 정확도나 감정 판정이 아닙니다. 입력 뒤 파일과 동의가 초기화됩니다.'),
      (23, '04  놓친 사례도 함께 공개', '다른 ESC-50 Dog 자료 · 동일 모델',
       'Dog 원본인데 44.5/100\n기준에 못 미쳐 놓침.\n\n에너지 짖음 후보와\nLSTM 결과가 다를 수 있음.\n시연 의견 ≠ 정답 라벨.',
       'verified_browser_audio_review.png', browser_footer,
       '다른 개 소리 음원은 모델 점수가 사십사 점 오로 기준보다 낮았습니다. 놓친 사례도 그대로 보여줍니다. 에너지 기반 짖음 후보와 엘에스티엠 점수는 다른 신호입니다.'),
      (22, '05  귀가 요약과 출처', '서버가 저장된 분석 구간을 집계',
       '앞의 놓친 사례 외출 요약\n분석 표본 5초\n판단 불가 5초\n짖음 후보 1회\n\n공개 시연 표본 5초와\n관찰 #2 근거를 함께 표시.',
       'verified_browser_summary.png', browser_footer,
       '이 화면은 놓친 사례 한 건의 귀가 요약입니다. 성공 사례는 포함하지 않습니다. 분석 표본 오 초와 영상 판단 불가 오 초, 공개 시연 출처를 근거와 함께 표시합니다.'),
      (22, '06  자연스러운 질문과 RAG', '“얼마나 오래 봤는지 알려줘”',
       '표본 시간·판단 불가·\n시연 출처만 검색.\n\n답마다 관찰 #2로\n돌아가는 근거 링크.',
       'verified_browser_duration_question.png', browser_footer,
       '얼마나 오래 봤는지 묻자, 분석 표본 오 초와 판단 불가 오 초, 공개 자료 출처를 각각 근거 번호와 함께 제시합니다. 관련 없는 정보는 질문에서 빼었습니다.'),
      (24, '07  모델 비교와 채택 판단', '검증 향상과 평가 성능은 구분',
       'FSD50K 평가에서 후보가 하락.\n운영 체크포인트는 유지.\n실제 가정 성능으로 주장하지 않음.',
       None, '고정 평가 자료 · 개발 실험 결과 · 실제 가정 정확도 아님',
       '증강 후보의 검증 점수는 좋아졌지만, 에프 에스 디 평가의 에프 원은 기존 영 점 사 삼 육에서 후보 영 점 사 삼 영으로 낮아졌습니다. 그래서 운영 모델을 바꾸지 않았습니다.'),
      (24, '08  다음 검증', '현장 데이터와 사용자 확인이 필요',
       '실제 반려견의 생활 음향\n시간별 사람 정답\n가정·개체별 독립 평가\n\n현재 화면은 로컬 시제품.',
       None, '연속 클릭 시연은 로컬 앱에서 별도 진행 · 녹화 완료로 주장하지 않음',
       '다음 단계는 실제 반려견의 생활 음향을 받아 시간별 정답을 붙이고, 가정과 개체를 분리해 평가하는 것입니다. 이번 영상은 실제 브라우저 캡처를 편집한 설명 영상입니다.'),
    ]
    paths, starts, total = [], [], 0
    for index, (duration, title, section, note, screenshot, footer, _) in enumerate(parts):
        for name in [screenshot] if screenshot else []:
            if not (IMAGES/name).is_file():
                raise FileNotFoundError(IMAGES/name)
        paths.append(slide(index, title, section, note, screenshot, footer,
                           metrics if index == 6 else None))
        starts.append(total)
        total += duration
    sample_rate = 48000
    sound = np.zeros((total*sample_rate, 2), dtype=np.float32)
    for i, (duration, *_, narration) in enumerate(parts):
        voice = speech(narration, i, sample_rate)
        offset = (starts[i] + 2)*sample_rate
        if offset + len(voice) > (starts[i] + duration - 2)*sample_rate:
            raise ValueError(f'narration {i} exceeds the slide duration')
        sound[offset:offset+len(voice)] += voice[:, None]*.8
    dog = ROOT/'artifacts/datasets/esc50_demo/audio/5-203128-A-0.wav'
    if not dog.is_file():
        raise FileNotFoundError('Run python -m scripts.prepare_demo_audio before building the video')
    if hashlib.sha256(dog.read_bytes()).hexdigest() != SAMPLES[dog.name][2]:
        raise ValueError('public audio hash changed')
    audio, rate = sf.read(dog, dtype='float32', always_2d=True)
    audio = audio.mean(axis=1)
    if rate != sample_rate:
        from math import gcd
        factor = gcd(rate, sample_rate)
        audio = resample_poly(audio, sample_rate//factor, rate//factor)
    offset = (starts[2] + 19)*sample_rate
    sound[offset:offset+len(audio)] += audio[:, None]*.6
    wave = OUT/'genesis_walkthrough_sound.wav'
    sf.write(wave, np.clip(sound, -1, 1), sample_rate, subtype='PCM_16')
    playlist = OUT/'genesis_slides.txt'
    lines = []
    for i, path in enumerate(paths):
        lines += [f"file '{path.as_posix()}'", f'duration {parts[i][0]}']
    lines.append(f"file '{paths[-1].as_posix()}'")
    playlist.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    output = OUT/'petmind_genesis_browser_walkthrough.mp4'
    subprocess.run([get_ffmpeg_exe(), '-y', '-f', 'concat', '-safe', '0', '-i', str(playlist),
                    '-i', str(wave), '-map', '0:v', '-map', '1:a', '-r', '12',
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k',
                    '-t', str(total), str(output)], check=True, capture_output=True)
    print(output)


if __name__ == '__main__':
    main()
