# YAMNet 특징과 음성 LSTM 비교 실험

## 목적과 구현

기존 5초 log-mel LSTM의 짖음 놓침을 줄일 수 있는지 확인하고, LSTM이 시간 정보를 실제로 활용하는지 검증했다. 운영 API와 모델은 바꾸지 않았다. 별도 실험 환경에서 [공식 YAMNet](https://tfhub.dev/google/yamnet/1)의 시간순 1024차원 임베딩을 추출하고, PyTorch의 작은 LSTM이 이를 받아 5초 창의 짖음 후보를 판별하도록 구현했다. 시간순 특징을 평균 내는 분류기를 같은 입력의 대조군으로 학습했다. YAMNet 단독 Bark 점수, 기존 LSTM, 두 모델의 OR도 비교했다. YAMNet의 공식 클래스에는 Bark·Doorbell·Knock가 각각 존재한다([클래스 목록](https://github.com/tensorflow/models/blob/master/research/audioset/yamnet/yamnet_class_map.csv)).

FSD50K의 **명시적 `Bark` 라벨**만 양성으로 사용했다. `Dog`만 붙은 음원과 ESC-50 `dog`는 짖음 정답으로 바꾸지 않고 제외했다. 음성 대조군은 FSD50K의 비개 관련 음원 전체와 공식 분할별 ESC-50 비개 소리 80개다. 원본 ID·SHA-256을 검사하고 학습 232개(양성 32), 검증 182개(양성 42), 사후 평가 182개(양성 42)를 분리했다. FSD 라벨은 음원 단위이며 짖음 시작·종료의 정답이 아니다. [FSD50K](https://zenodo.org/records/4060432), [ESC-50](https://github.com/karolpiczak/ESC-50)

YAMNet은 고정한 채 16 kHz 음원의 5초 창마다 약 0.96초 패치의 특징을 순서대로 추출했다. 임베딩 정규화는 **학습 분할에서만** 계산했다. 검증 F1을 최대화하되 비개 소리 오탐률 5% 이하인 임계값·학습 epoch를 선택한 후 평가 분할을 한 번 보고했다. 기존 LSTM은 운영 임계값 0.9와 검증 자료에서만 재선정한 임계값을 구분해 표시했다. YAMNet 모델의 `saved_model.pb` SHA-256은 `672af6e1e34fe15a42d45d70217fd39f97e10aef9b0effbf9b0bf7826fccd462`다. 출처별 목록·특징·체크포인트·전체 수치는 Git 제외 `artifacts/yamnet_bark_experiment/`에 있다.

## 같은 182개 평가 음원에서의 결과

| 모델 | 정밀도 | 재현율 | F1 | 오탐 FP | 놓침 FN |
|---|---:|---:|---:|---:|---:|
| 기존 log-mel LSTM, 임계값 0.9 | 0.857 | 0.286 | 0.429 | 2 | 30 |
| 기존 LSTM, 검증 임계값 재선정 | 0.645 | 0.476 | 0.548 | 11 | 22 |
| YAMNet Bark 점수 단독 | **0.935** | **0.690** | **0.795** | 2 | 13 |
| YAMNet 임베딩 평균 분류기 | 0.756 | 0.738 | 0.747 | 10 | 11 |
| YAMNet 임베딩 → LSTM | **0.966** | 0.667 | 0.789 | **1** | 14 |
| 기존 LSTM 또는 YAMNet, OR | 0.879 | 0.690 | 0.773 | 4 | 13 |

이 실험에서는 YAMNet 단독의 F1이 가장 높았다. 결합 LSTM은 YAMNet 단독보다 오탐이 1개 적지만 짖음을 1개 더 놓쳐 F1은 조금 낮다. 기존 LSTM만 맞힌 짖음은 **0개**, YAMNet만 맞힌 짖음은 **17개**여서 단순 병렬 결합은 이 자료에서 도움이 되지 않았다. 시간순 패치를 역순으로 넣으면 결합 LSTM의 F1이 **0.789→0.747**, 오탐은 **1→5개**로 변했다. 순서에 반응한다는 근거이지만, 이것만으로 더 좋은 운영 모델임을 증명하지는 못한다.

기존 README의 FSD50K `Dog` 라벨 기반 28.3% 재현율과 이번 **Bark만 양성인 182개** 실험은 대상이 다르므로 같은 평가 점수처럼 비교하지 않는다. 또한 ESC·FSD 평가 자료는 이전에 이미 확인했고, YAMNet의 AudioSet 사전학습과 FSD Freesound 원본이 겹쳤을 가능성을 배제하지 못했다. 따라서 위 표는 **개발용 사후 비교**이며 새로운 독립 성능이나 실제 가정 정확도가 아니다. 양성 평가 42개와 선택된 음성 대조군은 가정 환경의 자연 발생 빈도를 대표하지 않는다.

## 기존 방문 상황 시연 음원에 적용

초인종 0.2~2.6초, 노크 2.8~4.3초, 공개 짖음 5~10초로 만든 기존 10초 음원을 별도로 분석했다. YAMNet의 첫 5초 Doorbell 최고 점수는 **0.989**, Knock은 **0.025**였다. 둘째 5초 Bark 점수는 **0.794**였다. 새 임베딩 LSTM은 첫 창 **0.213(기타 후보)**, 둘째 창 **0.786(짖음 후보)**를 냈다(검증 선택 임계값 0.55). 노크는 이번 음원에서 **자동 감지됐다고 주장할 수 없다**. 점수는 보정된 확률이나 정확한 발성 시각이 아니며, 실제 방문자를 확인하지도 않는다. 상세 결과는 `visitor_scene.json`과 `visitor_predictions.json`에 있다.

## 실행과 결정

저장소 루트에서 기존 음원 다운로드·분할을 준비한 뒤 다음을 실행한다. TensorFlow는 기존 백엔드 의존성을 건드리지 않도록 Git 제외 실험 환경에 설치한다.

```powershell
python -m venv artifacts/yamnet_env
artifacts/yamnet_env/Scripts/python.exe -m pip install -r requirements-yamnet-experiment.txt
python -m scripts.prepare_yamnet_bark_experiment
artifacts/yamnet_env/Scripts/python.exe -m scripts.extract_yamnet_bark_features
python -m scripts.train_yamnet_bark_lstm
artifacts/yamnet_env/Scripts/python.exe -m scripts.check_yamnet_visitor_scene
python -m scripts.check_yamnet_visitor_prediction
```

실제 검증: 특징 추출 596개 완료, 시연 음원 두 창 모두 추론, 전체 Python 테스트 **153개 통과**, 실험 환경 `pip check` 정상. Windows PC에서 YAMNet 모델을 미리 로드한 뒤 평가 음원 182개의 특징 추출은 약 **3.25초**였다. PyTorch 결합 LSTM의 저장 특징 추론은 약 **0.008초**였지만 두 수치를 합친 값이 실제 Pi 지연은 아니다. Pi 메모리·지연·동기화는 아직 검증하지 않았다.

**결정:** 새 모델은 실험 체크포인트로만 보존하고 운영에 연결하지 않는다. 독립적인 가정 음원과 명시적 짖음 정답을 확보한 뒤 YAMNet 단독과 임베딩 LSTM을 재평가한다. 그때도 LSTM이 단독 모델보다 의미 있는 이득을 보이지 않으면 YAMNet 단독을 채택하는 편이 타당하다.
