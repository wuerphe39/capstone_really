# 초인종·노크·개 짖음 소리 순서의 RAG 시연

기존 첫 번째 발표 사례를 **초인종 → 노크 → 개 짖음 소리**가 차례로 들리는 10초 음원으로 다시 만들었다. 이번 사례에서는 모델 판단을 맞추기 위한 시연 담당자 의견이나 보호자 확인 표시를 입력하지 않았다. 웹 UI에서 파일을 직접 업로드한 뒤 음성 LSTM 분석, 귀가 요약, Gemini 기반 기록 검색 답변과 다음 확인 제안을 녹화했다. 근거 버튼을 눌러 별도 창을 여는 장면은 영상에서 제외했다.

## 음원과 출처

| 구간 | 소리 | 원본·권리 |
|---|---|---|
| 0.2~2.6초 | 초인종 | [Wikimedia Commons, Amada44](https://commons.wikimedia.org/wiki/File:Sound_Effect_-_Door_Bell.ogg), CC0 1.0 |
| 2.8~4.274초 | 노크 | [Wikimedia Commons, Mx. Granger](https://commons.wikimedia.org/wiki/File:Door_knocker_audio.ogg), CC0 1.0 |
| 5~10초 | 개 짖음 소리 | [FSD50K](https://zenodo.org/records/4060432) ID 15791, 업로더 laurent, CC BY 3.0 |

`scripts/prepare_visitor_bark_demo.py`가 16 kHz WAV를 만들고 원본 URL·라이선스·SHA-256·구간을 Git 제외 `artifacts/ai_sound_demo_20261012/visitor/manifest.json`에 저장한다. 생성된 WAV의 SHA-256은 `e08aab0ecb2575ec5f2cd1f845f8cc772791aede2c9d2d5d2c273875eca8461a`다. 서로 다른 공개 녹음을 배치한 **합성 시연**이므로 실제 방문자 또는 짖음의 원인이 확인된 사례가 아니다.

## 실제 실행 결과

실험용 `household_bark_candidate.pt`와 기준값 0.9로 분석한 결과, 0~5초 창은 개 짖음 소리 점수 **0.060**으로 다른 소리 후보, 5~10초 창은 **0.960**으로 개 짖음 소리 후보였다. 점수는 보정된 확률이나 정확도가 아니며, 5초 창은 정확한 짖음 시작 시각·횟수가 아니다. 이번 음원 한 개는 독립 성능 평가가 아니다.

브라우저에서 **파일 선택 → 상황 설명 입력 → 저장 동의 → 업로드·분석 → 귀가 요약 → RAG 질문** 순서로 수행했다. 화면 입력란 이름도 `시연 음원 설명`으로 바꿨다. 여기에 출처 ID와 라이선스 대신 **“집에 초인종 소리가 나고 노크 소리가 들린 뒤 개가 짖는 소리가 들립니다.”**라는 문장만 썼다. 원본 출처는 위 표와 manifest에 따로 기록한다. 확인 의견을 입력하지 않아 관찰 상태는 `시연 담당자 확인 전`이다. Gemini `gemini-3.5-flash-lite`의 사실 선택 호출은 실패 없이 로컬 기록에서 **입력한 상황 설명**, **LSTM의 2개 창 중 1개 후보**, **공개 시연 범위**를 별도 근거로 선택했다. RAG에는 “초인종과 노크 뒤 개 짖음 소리 후보가 나타났나요? 어떤 근거가 있고 실제 방문자 때문에 짖었다고 단정할 수 있나요?”라고 질문했다.

화면의 다음 확인 제안은 상황 설명과 모델 결과를 대조해 **실제 가정에서 유사한 순서가 관찰되면 현관 영상·방문 기록과 시각을 비교**하도록 안내한다. **방문자의 존재나 짖음 원인을 이 음원만으로 확정하지 않는다.** 이 문장은 Gemini의 자유 생성 처방이 아니라 서버의 근거 연결 규칙으로 작성된다. 초인종·노크 구분 자체도 현재 LSTM이 판별한 결과가 아니라 업로드 담당자가 입력한 설명이다.

## 영상과 재현

새 첫 번째 영상은 `artifacts/ai_sound_demo_20261012/visitor/PetMind_visitor_doorbell_knock_bark_RAG.mp4`다. 앞 10초는 실제 업로드한 시험 음원이 들리고, 이어 실제 Flutter 브라우저 조작과 RAG 답변·다음 확인 제안을 보여준다. 마지막 결과 화면에도 근거 별도 창은 넣지 않았다. 이전 `natural/PetMind_case_1_detected.mp4`는 과거 시연 기록이며 발표에는 **새 영상을 사용**한다.

재현 순서는 `python -m scripts.prepare_visitor_bark_demo`, 별도 DB와 실험 체크포인트를 설정한 API·Flutter 웹 실행, `node scripts/record_natural_voice_cases.cjs --visitor`, `python -m scripts.build_visitor_bark_video`다. 브라우저 결과 원문은 `visitor/visitor_ui_result.json`에 있다. 공개 음원·개인 DB·모델 파일·녹화 결과는 Git에 올리지 않는다.

검증: 시연용 별도 DB에 웹 업로드 관찰 1건이 저장됐고, Gemini 응답에는 상황 설명(`scene.1`)과 실제 LSTM 창 수(`current.audio_lstm`)가 함께 포함됐다. 시연 담당자 의견은 저장되지 않았다. 완성된 MP4는 1280×720, 약 55.0초이며 H.264 영상과 AAC 음성 스트림을 포함하고 FFmpeg 전체 디코딩 오류가 없었다. 전체 Python 회귀 테스트 **151개 통과**, Flutter 테스트 **21개 통과**, `flutter analyze` 문제 없음, Flutter 웹 빌드 성공 및 `git diff --check` 오류 없음.
