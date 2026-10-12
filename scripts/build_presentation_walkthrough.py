"""Render an honestly labeled presentation walkthrough from verified demo UI captures.

This is a fallback when browser screen recording is unavailable. It is not a
screen recording: Flutter widgets are rendered from a saved public-demo API
fixture. Source WAV and output MP4 remain in ignored artifacts/.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf
from PIL import Image, ImageDraw, ImageFont
from imageio_ffmpeg import get_ffmpeg_exe
from scipy.signal import resample_poly


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "presentation_20261011"
FONT = Path(r"C:\Windows\Fonts\malgun.ttf")
BOLD = Path(r"C:\Windows\Fonts\malgunbd.ttf")
SCREEN = (1920, 1080)


def font(size: int, bold: bool = False):
    return ImageFont.truetype(str(BOLD if bold else FONT), size)


def lines(draw, text, xy, size=31, color="#e8e5f2", step=None, bold=False):
    x, y = xy
    for line in text.split("\n"):
        draw.text((x, y), line, font=font(size, bold), fill=color)
        y += step or round(size * 1.55)
    return y


def slide(name, section, title, note, screenshot=None, footer="", emphasis=None):
    image = Image.new("RGB", SCREEN, "#101018")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((42, 36, 1878, 1044), radius=28, fill="#1c1b24", outline="#4c415e", width=2)
    draw.text((84, 63), "PetMind  |  공개 음원 검증·시연", font=font(27, True), fill="#cdb9ff")
    draw.text((84, 115), title, font=font(53, True), fill="#ffffff")
    draw.text((84, 188), section, font=font(27), fill="#d2cde0")
    if screenshot:
        shot = Image.open(OUT / screenshot).convert("RGB")
        shot.thumbnail((1215, 670), Image.Resampling.LANCZOS)
        frame = (66, 256, 66 + shot.width + 20, 256 + shot.height + 20)
        draw.rounded_rectangle(frame, radius=17, fill="#0b0b10", outline="#605574", width=2)
        image.paste(shot, (76, 266))
        x = 1330
    else:
        x = 100
    lines(draw, note, (x, 277), size=31, step=57)
    if emphasis:
        y = 810 if screenshot else 665
        draw.rounded_rectangle((x - 15, y - 18, 1840, y + 120), radius=17, fill="#342d45")
        lines(draw, emphasis, (x, y), size=26, color="#f4d3a8", step=49, bold=True)
    draw.line((84, 965, 1836, 965), fill="#4c415e", width=2)
    draw.text((84, 987), footer or "공개 데이터 재현 화면 · 별도 시연 DB · 실제 보호자 기록 아님", font=font(24), fill="#bdb3ce")
    path = OUT / f"slide_{name}.png"
    image.save(path)
    return path


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    metrics = json.loads((ROOT / "docs/evidence/audio_lstm_three_way.json").read_text(encoding="utf-8"))
    demo = json.loads((ROOT / "docs/evidence/presentation_demo_api.json").read_text(encoding="utf-8"))
    assert metrics["promoted"] is False
    assert demo["summary"]["bark_candidate_count"] == 6
    slides = [
        ("00", 18, "01  문제와 목표", "개 소리 감지 결과를 반려견별 관찰 기록과 연결", "개 소리만으로 감정·질환을\n단정할 수 없습니다.\n\n소리 후보 → 보호자 의견\n→ 귀가 요약 → 원본 근거\n흐름을 검증합니다.", None,
         "이 영상은 실제 API 자료의 Flutter 렌더 화면으로 만든 설명 영상입니다."),
        ("01", 22, "02  공개 자료와 검증 분할", "ESC-50 · FSD50K 원본 단위 분리", "ESC 공식 train/val/test\nFSD 공식 dev/train·val·eval\n\n원본 ID·SHA256 중복 검사\n검증 자료로만 후보 선택\n평가 자료는 사후 비교용", None,
         "FSD val 110건 새로 확보\n원본 WAV는 Git 제외"),
        ("02", 22, "03  음원 입력과 출처", "공개 자료 여부와 보관·학습 동의를 분리", "WAV 입력 → 출처 기재\n시연용 자료로 표시\n학습 동의는 비활성화\n\n실제 반려견 장기 기록과\n섞지 않도록 별도 DB 사용", "public_audio_form.png", None),
        ("03", 25, "04  감지 사례와 구간 재생", "ESC Dog 음원 · 기존 LSTM 후보 점수 0.939", "5초 분석 창마다\n후보·모델 점수·의견 표시\n\n구간 듣기에서 원본 재생\n정확한 발성 시각으로\n표현하지 않습니다.", "public_audio_timeline.png", "이 구간에서 원본 Dog 음원 재생"),
        ("04", 28, "05  놓침과 환경음", "성공 사례만 고르지 않은 시연", "Dog 원본인데 점수 0.040\n→ 기존 모델의 놓침\n\nRain 원본 점수 0.010\n→ 기타 소리 후보\n\n에너지 짖음 후보와 LSTM\n판정은 구분합니다.", "public_audio_timeline.png", "시연 담당자 의견은\n모델 정답이 아닙니다."),
        ("05", 23, "06  귀가 요약", "코드가 저장 구간 수치를 먼저 계산", "두 번째 외출 분석 표본 10초\n판단 불가 10초\n짖음 후보 6회\n\n외출 전체 시간의 활동량은\n계산하지 않습니다.", "public_outing_summary.png", None),
        ("06", 23, "07  기록 검색과 근거", "RAG 검색 mcp · 설명 grounded-template", "관찰 #2·#3을 인용\n모델 놓침·Rain 의견 반영\n원본 음원 링크 제공\n\n'보호자가 TV 확인' 질문엔\n근거 부족으로 답합니다.", "public_rag_evidence.png", None),
        ("07", 30, "08  동일 조건 모델 비교", "검증 점수 향상과 배포 판단을 분리", "검증 평균 F1\n기존 0.663\n임계값 조정 0.698\n증강·MIL 0.746\n\nFSD 평가 F1\n기존 0.436 → 후보 0.430", None,
         "운영 체크포인트 유지\n평가 하락 후보 미적용"),
        ("08", 25, "09  한계와 다음 단계", "기록은 쌓았지만 실제 가정 성능은 미검증", "FSD Dog 60건 중 43건 놓침\nESC Dog 평가 표본은 8건\n\n같은 반려견·홈캠 음원으로\n사람이 시간별 정답을 붙인\n독립 평가가 다음 과제입니다.", None,
         "감정·질환 진단이나\n발성 3종 분류를 주장하지 않음"),
    ]
    narration = [
        "펫마인드는 소리만으로 반려견의 감정이나 질환을 단정하지 않습니다. 관찰 후보를 기록하고, 사람의 의견과 원본 근거를 함께 보여줍니다.",
        "공개 자료는 원본 단위로 분리했습니다. 검증 자료에서만 후보를 선택했고, 평가 자료는 선택 뒤에 비교했습니다. 새로 확보한 에프에스디 검증 음원은 백십 건입니다.",
        "음원은 출처와 함께 시연용으로 표시합니다. 공개 자료의 의견은 실제 보호자의 확인이 아니고, 공통 모델 학습 동의에도 포함하지 않습니다.",
        "첫 사례는 개 소리 후보로 감지됐습니다. 화면의 오 초 창은 분석 단위이지, 정확한 짖음 시작과 끝이 아닙니다. 이제 원본 소리를 들려드립니다.",
        "두 번째 개 소리는 기존 모델이 놓쳤습니다. 비 소리는 기타 후보였습니다. 에너지 감지의 짖음 후보와 엘에스티엠 결과가 다를 수 있으므로 각각 구분해 보여줍니다.",
        "귀가 요약은 저장된 분석 표본을 코드로 집계합니다. 두 번째 외출의 표본은 십 초이고, 영상 판단 불가도 십 초입니다. 외출 전체 활동량이라는 뜻은 아닙니다.",
        "기록 검색은 관찰 번호와 원본 링크를 근거로 답합니다. 시연 담당자의 의견을 보호자 확인으로 바꿔 말하지 않으며, 근거가 없는 티브이 질문에는 부족하다고 답합니다.",
        "증강 후보의 검증 평균 에프 원은 좋아졌지만, 기존 에프에스디 평가 성능은 낮아졌습니다. 따라서 운영 체크포인트는 기존 모델을 유지했습니다.",
        "공개 음원 결과를 실제 가정 성능이라고 주장하지 않습니다. 다음에는 같은 반려견의 생활 음향을 모으고, 사람이 시간별 정답을 붙인 독립 평가가 필요합니다.",
    ]
    concat = []
    starts = []
    elapsed = 0
    for name, duration, title, section, note, screenshot, emphasis in slides:
        path = slide(name, section, title, note, screenshot, emphasis=emphasis)
        concat.extend([f"file '{path.as_posix()}'", f"duration {duration}"])
        starts.append(elapsed)
        elapsed += duration
    concat.append(f"file '{(OUT / 'slide_08.png').as_posix()}'")
    list_file = OUT / "slides.txt"
    list_file.write_text("\n".join(concat) + "\n", encoding="utf-8")
    dog = ROOT / "artifacts/datasets/esc50/audio/5-203128-A-0.wav"
    if not dog.is_file():
        raise FileNotFoundError(dog)
    sample_rate = 48000
    sound = np.zeros((elapsed * sample_rate, 2), dtype=np.float32)
    for i, (start, script) in enumerate(zip(starts, narration)):
        text_path = OUT / f"narration_{i:02d}.txt"
        wave_path = OUT / f"narration_{i:02d}.wav"
        text_path.write_text(script, encoding="utf-8")
        subprocess.run(["powershell", "-NoProfile", "-File", str(ROOT / "scripts/synthesize_walkthrough.ps1"),
                        "-TextPath", str(text_path), "-WavePath", str(wave_path)], check=True, capture_output=True)
        voice, rate = sf.read(wave_path, dtype="float32")
        if voice.ndim == 2:
            voice = voice.mean(axis=1)
        if rate != sample_rate:
            from math import gcd
            factor = gcd(rate, sample_rate)
            voice = resample_poly(voice, sample_rate // factor, rate // factor)
        offset = (start + 2) * sample_rate
        if offset + len(voice) > (start + slides[i][1] - 1) * sample_rate:
            raise ValueError(f"narration {i} exceeds its slide duration")
        sound[offset:offset + len(voice)] += voice[:, None] * 0.8
    dog_audio, dog_rate = sf.read(dog, dtype="float32", always_2d=True)
    dog_audio = dog_audio.mean(axis=1)
    if dog_rate != sample_rate:
        from math import gcd
        factor = gcd(dog_rate, sample_rate)
        dog_audio = resample_poly(dog_audio, sample_rate // factor, dog_rate // factor)
    dog_offset = (starts[3] + 18) * sample_rate
    sound[dog_offset:dog_offset + len(dog_audio)] += dog_audio[:, None] * 0.65
    wave = OUT / "walkthrough_sound.wav"
    sf.write(wave, np.clip(sound, -1, 1), sample_rate, subtype="PCM_16")
    output = OUT / "petmind_public_data_walkthrough.mp4"
    ffmpeg = get_ffmpeg_exe()
    command = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-i", str(wave),
               "-map", "0:v", "-map", "1:a", "-r", "12", "-c:v", "libx264", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "128k", "-shortest", str(output)]
    subprocess.run(command, check=True, capture_output=True)
    print(output)


if __name__ == "__main__":
    main()
