# AudioSet 구간 정답을 이용한 YAMNet 임베딩 LSTM 재학습

## 목적과 자료

기존 YAMNet 임베딩 LSTM의 학습용 짖음 자료가 적어, [AudioSet의 시간 구간별 정답](https://research.google.com/audioset/download_strong.html) 중 공식 **train** 분할의 `Bark`를 추가했다. AudioSet이 배포하는 128차원 VGGish 특징은 YAMNet 임베딩이 아니므로 사용하지 않았다. 접근 가능한 원본 음원에서 16kHz 단일 채널 WAV를 만들고, 같은 YAMNet 체크포인트로 1,024차원 시간순 임베딩을 추출했다. [YAMNet 임베딩 설명](https://www.tensorflow.org/tutorials/audio/transfer_learning_audio), [AudioSet 형식](https://research.google.com/audioset/download.html).

- AudioSet strong train의 `Bark`: 6,240개 구간 정답, 1,636개 음원 후보.
- 무작위가 아닌 고정 해시 순서로 최대 짖음 40개, 비짖음 40개를 받았다. 비짖음 후보에는 초인종·노크·말소리·TV를 포함했지만, 최종 29개에는 초인종 3개·말소리 11개·TV 16개가 있고 **노크는 0개**다(복수 라벨 가능). 노크 오탐 개선은 이 실험으로 검증하지 못했다.
- 삭제·접근 제한·짧은 음원을 제외한 실제 유효 자료: **64개 음원(짖음 포함 35, 비짖음 29)**. 서로 다른 YouTube 영상 64개이며 WAV 해시도 모두 다르다.
- 각 10초 음원을 5초 창 2개로 분할했다. 구간 정답과 0.1초 이상 겹친 창을 짖음으로 지정한 결과 **짖음 54창, 비짖음 74창**이다.
- 추가 자료는 **학습에만** 사용했다. 기존 FSD50K·ESC-50 검증·평가 자료와 선택 규칙은 유지했다. 추가 자료와 검증·평가 음원의 파일 해시 일치는 0건이다. 원본 내용이 다른 형식으로 재업로드된 경우까지 배제한 것은 아니다.
- 원본 음원·임베딩·체크포인트·개별 실패 기록은 Git에서 제외된 `artifacts/audioset_bark_strong/`에 저장했다. `manifest.json`에 영상 ID·구간·해시·접근 실패 내역이 있다.

## 동일 평가 자료의 결과

검증 자료에서만 임계값과 학습 epoch를 선택했다. 아래 평가 자료 182개 중 짖음 42개이며, 이 자료는 이전 실험에서도 확인한 **개발용 평가**다. 새로운 독립 테스트로 해석하지 않는다.

| 방법 | 정밀도 | 재현율 | F1 | TP | FP | FN |
|---|---:|---:|---:|---:|---:|---:|
| YAMNet `Bark` 직접 점수 | 0.935 | 0.690 | 0.795 | 29 | 2 | 13 |
| 기존 YAMNet 임베딩 LSTM | 0.966 | 0.667 | 0.789 | 28 | 1 | 14 |
| AudioSet 추가 LSTM, 시드 20261012 | 0.886 | 0.738 | 0.805 | 31 | 4 | 11 |
| AudioSet 추가 LSTM, 시드 11 | 0.800 | 0.762 | 0.780 | 32 | 8 | 10 |
| AudioSet 추가 LSTM, 시드 29 | 0.938 | 0.714 | 0.811 | 30 | 2 | 12 |

추가 학습으로 짖음을 더 찾는 실행이 있었지만 오탐도 늘었고, 시드에 따라 YAMNet 단독보다 낮은 결과가 나왔다. 첫 시드의 검증 F1은 1.000이지만 평가 F1은 0.805로 떨어졌다. 이 차이는 과적합이나 자료 분포 차이의 신호일 수 있다. 원인은 아직 확정하지 않았다. **개선이 안정적으로 확인되지 않아 운영 모델을 교체하지 않았다.**

## 검증 범위와 다음 단계

YAMNet 자체가 AudioSet으로 사전학습됐으므로 AudioSet 음원을 독립 평가로 쓰지 않았다. 기존 FSD50K·ESC-50 평가도 이미 확인한 자료이며 AudioSet과 음원 내용의 잠재적 중복을 완전히 배제하지 못한다. 평가 자료의 비짖음 비율과 집 안 실제 환경의 비율도 다르다. 따라서 위 수치를 홈캠·마이크 실제 정확도로 제시하지 않는다.

다음에는 **손대지 않은 가정 환경 음원**을 짖음·초인종·말소리·TV와 함께 확보하고, 영상/녹음 원본별로 학습·검증·평가를 분리해야 한다. 그 자료에서 여러 시드의 정밀도·재현율·오탐을 비교하고 개선이 재현될 때에만 LSTM을 채택한다.

재현 명령(프로젝트 루트에서 실행):

```powershell
python -m pip install -r requirements-audioset-experiment.txt
python -m scripts.prepare_audioset_bark_strong
artifacts\yamnet_env\Scripts\python.exe -m scripts.extract_yamnet_bark_features --root artifacts/audioset_bark_strong
..\petmind_integrated\.venv\Scripts\python.exe -m scripts.train_audioset_bark_lstm
..\petmind_integrated\.venv\Scripts\python.exe -m scripts.train_audioset_bark_lstm --seed 11
..\petmind_integrated\.venv\Scripts\python.exe -m scripts.train_audioset_bark_lstm --seed 29
```

실제 확인: 새 데이터 선택·창 라벨 테스트를 포함한 Python 회귀 테스트 **154개 통과**. Flutter UI와 운영 추론 경로는 변경하지 않았다.
