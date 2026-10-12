"""Package the actual browser recording with the ordered visitor-scene audio."""
import json
from pathlib import Path

from scripts import build_natural_case_videos as video


FOLDER = Path('artifacts/ai_sound_demo_20261012/visitor').resolve()


def main():
    video.FOLDER = FOLDER
    rows = json.loads((FOLDER / 'visitor_ui_result.json').read_text(encoding='utf-8'))
    if len(rows) != 1 or rows[0].get('error'):
        raise ValueError('A successful real web UI recording is required')
    row = rows[0]
    claims = {fact['id']: fact for fact in row['rag']['claims']}
    if row['rag']['failure'] or 'current.audio_lstm' not in claims or f"scene.{row['observation_id']}" not in claims:
        raise ValueError('RAG must cite both measured LSTM windows and the labeled source sequence')
    windows = row['model_windows']
    if len(windows) != 2:
        raise ValueError('Expected two measured five-second windows')
    first = video.still('visitor_opening', '초인종 → 노크 → 개 짖음 소리', [
        '집에 초인종 소리가 나고 노크 소리가 들린 뒤 개가 짖는 소리가 들립니다.',
        '이 음원을 웹 UI에 업로드하고 LSTM·RAG 결과를 확인합니다.',
        '시연 자료이며 방문자와 짖음의 원인은 확인되지 않았습니다.'
    ], 10, row['input'])
    ui = FOLDER / 'visitor_ui_with_silence.mp4'
    video.ffmpeg('-i', FOLDER / '1_visitor_sequence_ui.webm',
                 '-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=48000',
                 '-shortest', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-r', '25',
                 '-c:a', 'aac', '-ar', '48000', '-ac', '2', ui)
    last = video.still('visitor_closing', '실제 RAG 질문 결과', [
        f"0~5초 초인종·노크: LSTM 점수 {windows[0]['dog_score']:.3f}",
        f"5~10초 공개 짖음: LSTM 점수 {windows[1]['dog_score']:.3f}",
        'RAG는 음원 구성 메모와 모델 창을 서로 다른 근거로 표시했습니다.',
        '실제 방문자나 짖음의 원인은 이 자료만으로 단정하지 않습니다.'
    ], 10)
    listing = FOLDER / 'visitor_parts.txt'
    listing.write_text(''.join(f"file '{part.as_posix()}'\n" for part in (first, ui, last)),
                       encoding='utf-8')
    destination = FOLDER / 'PetMind_visitor_doorbell_knock_bark_RAG.mp4'
    video.ffmpeg('-f', 'concat', '-safe', '0', '-i', listing,
                 '-c', 'copy', '-movflags', '+faststart', destination)
    print(destination)


if __name__ == '__main__':
    main()
