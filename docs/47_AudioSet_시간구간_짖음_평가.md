# AudioSet 시간 구간 정답으로 짖음 놓침 분석

## 목적과 자료

[AudioSet의 시간 구간별 정답](https://research.google.com/audioset/download_strong.html) 중 공식 **eval** 분할을 사용해, 음원 전체에 짖음이 있는지와 짖음이 표시된 **5초 구간을 찾는지**를 따로 측정했다. 이미 학습한 모델과 임계값을 그대로 사용했고 이 자료로 재학습하거나 임계값을 선택하지 않았다.

YouTube 영상 삭제·접근 제한·10초 미만 음원을 제외하고 **53개 원본 영상**을 확보했다(짖음 포함 38개, 비짖음 15개). 5초 창으로 나누면 **106개 창**이며 짖음 구간과 0.1초 이상 겹치는 창 57개, 나머지 49개다. 짖음 창 중 23개는 정답 구간과 겹치는 시간이 1초 미만이다. AudioSet train과 eval 간 YouTube ID 및 WAV 파일 해시 중복은 없었다.

## 고정된 모델·임계값 비교

| 모델 | 5초 창 정밀도 | 5초 창 재현율 | 5초 창 F1 | 놓친 짖음 창 | 오탐 창 |
|---|---:|---:|---:|---:|---:|
| YAMNet `Bark` 직접 점수 | 0.913 | 0.737 | **0.816** | 15 | 4 |
| 기존 YAMNet 임베딩 LSTM | 0.842 | 0.561 | 0.674 | 25 | 6 |
| AudioSet 추가 LSTM, 시드 20261012 | 0.824 | 0.737 | 0.778 | 15 | 9 |
| AudioSet 추가 LSTM, 시드 11 | 0.759 | 0.719 | 0.739 | 16 | 13 |
| AudioSet 추가 LSTM, 시드 29 | 0.837 | 0.632 | 0.720 | 21 | 7 |

YAMNet 단독은 **1초 미만 짖음 창 23개 중 12개**를 놓쳤다. 1초 이상인 짖음 창 34개에서는 3개를 놓쳤다. 따라서 이 자료에서는 짧은 짖음이 가장 큰 놓침 집단이다. AudioSet을 추가 학습한 LSTM도 짧은 짖음 문제를 안정적으로 해결하지 못했다.

음원 단위로 두 5초 창 중 하나라도 찾았는지를 보면 YAMNet 단독은 짖음 음원 38개 중 30개를 찾았고, 비짖음 음원 15개에서는 오탐 0개였다. 하지만 **한 음원을 찾았다고 해서 짖은 시점까지 맞힌 것은 아니다.** UI에서 중요한 순간을 표시하려면 위의 구간별 결과를 더 중시해야 한다.

## 감지 기준만 낮추는 실험

AudioSet **train** 128개 창에서 YAMNet의 짖음 점수 임계값을 비교했다. 기존 0.05에서는 F1 0.792, 비짖음 오탐 7개였고, 0.02로 낮추면 F1 0.778, 오탐 12개였다. 짧은 짖음만 찾기 위해 단순히 기준을 낮추는 방법은 이 자료에서 유리하지 않았다. eval의 결과를 보고 임계값을 재선정하지 않았다.

## 더 짧은 특징 구간을 이용한 후보 실험

기존 5초 전체 판정 대신 YAMNet의 약 0.96초 특징을 0.48초 간격으로 추출하고, AudioSet의 짖음 시작·종료 정답을 해당 특징 구간에 투영해 **특징 구간별 LSTM**을 학습했다. 확보한 AudioSet train 음원 64개 중 영상 ID 기준 48개를 학습, 16개를 모델·임계값 선택에 사용했다. AudioSet eval은 선택에 쓰지 않았다.

같은 전체 10초 YAMNet 특징을 사용한 비교에서 후보 LSTM은 eval 짖음 57창 중 **45창 감지·12창 놓침**, 비짖음 오탐 **13창**, F1 **0.783**이었다. YAMNet `Bark` 직접 점수는 **42창 감지·15창 놓침**, 오탐 **6창**, F1 **0.800**이었다. 1초 미만 짖음 누락은 각각 10창과 11창이다. 짧은 짖음을 한 창 더 찾았지만 오탐이 크게 늘어 후보를 채택하지 않았다. 이 비교는 앞 표와 달리 YAMNet을 10초 연속으로 실행했으므로 경계 부근 점수가 조금 달라졌다.

해당 실험은 `scripts/extract_yamnet_patch_features.py`와 `scripts/train_yamnet_patch_lstm.py`로 재현할 수 있고, 결과는 Git 제외 경로 `artifacts/audioset_bark_strong/patch_lstm_comparison.json`에 남겼다.

## 해석과 다음 작업

이 실험은 오류 원인 분석이다. **YAMNet은 AudioSet으로 사전학습**됐으므로 이 AudioSet eval은 독립적인 일반화 정확도 검증이 아니다. 확보 가능한 YouTube 영상만 사용한 선택 편향이 있고 비짖음 음원도 15개뿐이다. 0.1초 이상 겹치면 5초 창을 양성으로 정한 규칙은 매우 짧은 짖음에서 평가를 어렵게 할 수 있다. 접근 가능한 원본 영상과 원래 주석 구간이 지금도 정확히 맞는지 청취 확인은 아직 하지 않았다.

다음 단계는 **더 다양한 1초 미만 짖음과 생활 소음의 구간 정답**을 확보하고, 오탐이 많이 나는 사례를 분리해 검증하는 것이다. 그 전에 낮은 점수를 받은 음원 일부를 청취해 정답과 현재 원본의 정렬이 맞는지 확인해야 한다. 새 후보는 시간당 오탐과 짧은 짖음 재현율을 함께 개선해야 한다. 지금은 모델 교체 근거가 없으므로 운영 경로를 변경하지 않았다.

## 재현

```powershell
python -m pip install -r requirements-audioset-experiment.txt
python -m scripts.prepare_audioset_bark_strong --split eval --positive 40 --negative 40
artifacts\yamnet_env\Scripts\python.exe -m scripts.extract_yamnet_bark_features --root artifacts/audioset_bark_strong_eval
..\petmind_integrated\.venv\Scripts\python.exe -m scripts.evaluate_audioset_strong_bark
artifacts\yamnet_env\Scripts\python.exe -m scripts.extract_yamnet_patch_features --root artifacts/audioset_bark_strong
artifacts\yamnet_env\Scripts\python.exe -m scripts.extract_yamnet_patch_features --root artifacts/audioset_bark_strong_eval
..\petmind_integrated\.venv\Scripts\python.exe -m scripts.train_yamnet_patch_lstm
```

실행 자료·각 창의 점수와 오류 목록은 Git에서 제외된 `artifacts/audioset_bark_strong_eval/comparison.json`에 저장했다. 구간 평가 테스트를 포함한 Python 회귀 테스트 **156개 통과**, `pip check` 정상.
