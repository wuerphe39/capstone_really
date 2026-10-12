# YAMNet 단독 비교 사이트

기존 PetMind 사이트(`http://localhost:8021/`)를 그대로 두고 별도 로컬 사이트(`http://localhost:8030/`)에서 **YAMNet의 Bark 점수만** 확인한다. LSTM·RAG·SQLite·카메라는 이 사이트의 판정에 참여하지 않는다. 업로드 파일도 저장하지 않는다.

저장소 루트에서 기존 실험용 TensorFlow 환경을 준비하고 실행한다.

```powershell
python -m venv artifacts/yamnet_env
artifacts/yamnet_env/Scripts/python.exe -m pip install -r requirements-yamnet-experiment.txt
artifacts/yamnet_env/Scripts/python.exe -m experimental.yamnet_only_site.app --port 8030
```

YAMNet 모델은 [공식 TensorFlow Hub 모델](https://tfhub.dev/google/yamnet/1)이며 처음 실행할 때 내려받을 수 있다. 입력은 30초·12MB 이하 WAV다. 16kHz 모노로 변환하고 5초마다 YAMNet을 호출한다. 각 구간의 `Bark` 패치 최고 점수를 표시하며, 후보 기준 **0.05**는 기존 FSD50K/ESC 검증 실험에서 정한 값을 고정 사용한다. 업로드 자료를 보고 기준을 바꾸지 않는다. 점수는 확률·정확도·짖음 횟수·정확한 발성 시각이 아니다.

`788196__mwf77__dog-barking.wav`의 로컬 기능 확인: 14.702초, 3개 창의 Bark 점수 **0.819 / 0.924 / 0.015**, 후보 **2개**. 같은 파일을 기존 운영 LSTM에 넣으면 **0.451 / 0.207 / 0.029**, 기준 0.9에서 후보 **0개**다. 이는 **이 음원 1개에 대한 비교**이며 실제 가정 환경의 전체 성능을 뜻하지 않는다. 평가 범위와 모델 채택 판단은 [YAMNet 비교](../../docs/45_YAMNet_임베딩_LSTM_비교.md), [시간 구간 평가](../../docs/47_AudioSet_시간구간_짖음_평가.md)에 있다.
