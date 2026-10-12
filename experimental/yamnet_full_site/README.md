# YAMNet → 기록 → RAG 전체 흐름 비교 사이트

기존 PetMind(LSTM 기본 설정, 웹 `8021`·API `8010`)와 별도로 같은 Flutter 화면을 웹 `8022`·API `8011`에서 실행한다. 음성 판별만 **YAMNet Bark**로 바꾸고, 외출 세션·관찰 저장·음원 구간 재생·보호자 의견·귀가 요약·기록 검색·케어 제안은 기존 코드를 재사용한다. 실험 기록과 원본은 `artifacts/yamnet_full_demo/`에 분리한다. `8030`은 YAMNet 분석 서비스와 간단한 점수 확인 페이지이며, 사용자가 시험할 전체 사이트는 `8022`다.

## 실행

저장소 루트에서 PowerShell 창 3개를 사용한다. Python 기본 환경에는 `requirements-core.txt`, YAMNet 환경에는 `requirements-yamnet-experiment.txt`가 필요하다. YAMNet 모델은 처음 실행할 때 공식 TensorFlow Hub에서 내려받을 수 있다.

```powershell
# 창 1 · YAMNet 로컬 분석 서비스
artifacts\yamnet_env\Scripts\python.exe -m experimental.yamnet_only_site.app --port 8030
```

```powershell
# 창 2 · 분리된 DB와 음원 저장소를 사용하는 API
$env:PETMIND_DATABASE_URL = 'sqlite:///artifacts/yamnet_full_demo/petmind_yamnet.db'
$env:PETMIND_AUDIO_STORAGE_DIR = 'artifacts/yamnet_full_demo/user_audio'
$env:PETMIND_AUDIO_DETECTOR = 'yamnet'
$env:PETMIND_YAMNET_URL = 'http://127.0.0.1:8030/analyze'
$env:PETMIND_LLM_PROVIDER = 'rule'
$env:PETMIND_SEMANTIC_SEARCH = 'off'
python -m uvicorn petmind.backend.main:app --host 127.0.0.1 --port 8011
```

```powershell
# 창 3 · 같은 Flutter 화면을 별도 API 대상으로 빌드·제공
cd petmind_app
$web = (Join-Path (Resolve-Path ..).Path 'artifacts\yamnet_full_demo\web')
flutter build web --release --no-web-resources-cdn --output=$web --dart-define=PETMIND_API_BASE=http://localhost:8011 --dart-define=PETMIND_YAMNET_TRIAL=true
cd ..
python -m http.server 8022 --bind 127.0.0.1 --directory $web
```

브라우저에서 `http://localhost:8022/`에 접속한다. `http://localhost:8011/health`의 `audio_detector`가 `yamnet`, 기본 `care_provider`가 `rule`인지 확인한다. 위 명령은 외부 전송 없이 MCP 기록 검색과 규칙 기반 요약·케어를 실행한다. **관찰 수치·시연 설명·확인 의견의 Google Gemini API 전송에 명시적으로 동의한 시험에서만** `$env:PETMIND_LLM_PROVIDER = 'gemini'`로 API를 시작한다. 원본 WAV는 Gemini 요청에 포함하지 않는다. Gemini 모드에서도 실제 답변 채택 여부는 화면의 제공자 표시로 확인한다. 응답 검증에 실패하면 규칙 제공자로 전환된다.

## 시험 흐름과 확인 결과

1. `외출·음원`에서 사용자 음원 모드 외출을 시작한다.
2. 공개 WAV라면 시연용 표시와 출처 설명을 입력하고, 저장 동의 후 30초 이하 WAV를 업로드한다.
3. 각 5초 창의 YAMNet Bark 점수와 후보 여부, 원본 구간을 확인한다. `반려견 소리`, `TV·외부 소리`, `판단하기 어려움` 등 담당자 확인 의견을 저장한다.
4. 외출을 종료해 귀가 요약의 분석 표본·후보 창 수·의견을 확인하고 `근거 기반 요약`을 실행한다. `RAG·케어`에서도 저장된 관찰에 관해 질문한다.

사용자가 제공한 `788196__mwf77__dog-barking.wav`로 로컬 기능 확인 시 길이는 14.702초였고, 5초 창의 YAMNet Bark 점수는 **0.819 / 0.924 / 0.015**, 고정 기준 0.05에서 **2/3개 창**이 후보였다. 분리된 DB에 관찰을 저장한 뒤 귀가 요약, 출처·모델 근거 검색, 케어 제안까지 API와 브라우저에서 확인했다. 명시적 승인 뒤 Gemini 3.5 Flash-Lite의 근거 선택과 생성형 케어 답변도 성공했다. 브라우저에서 `판단하기 어려움`이라는 시연 담당자 의견을 저장하자 Gemini 귀가 설명과 케어 제안에 반영됐다. 일부 생성 응답은 인용·형식 검증을 통과하지 못해 규칙 제공자로 전환됐으며, 화면에 실제 제공자를 표시한다. 기존 LSTM은 같은 파일에서 기준 0.9에 후보 0개였다. 한 음원의 차이이며 가정 환경 정확도나 개선 폭은 아니다.

이 음원에서 에너지 감지기가 기록한 **9개는 큰 소리 변화 구간**이며, 개 짖음 소리 판정이 아니다. 귀가 요약과 RAG·케어 설명은 모델이 분석한 **3개 창 중 후보 2개**를 우선 사용한다. 에너지 원시 수치는 진단용 분석 데이터에 보존하지만, 화면의 짖음 수치나 모델 근거로 제시하지 않는다. 모델이 실패하면 판별 불가를 표시한다.

YAMNet 점수는 확률·정확도·짖음 횟수가 아니다. 5초 창도 정확한 발성 시작·종료 시각이 아니다. `영상 행동 판단 불가` 시간은 영상 행동 분류의 부재를 뜻하며 음성 분석 실패 시간이 아니다. 카메라 연결과 Pi에서의 실시간 성능은 아직 검증되지 않았다. 기존 LSTM 데이터베이스와 모델 체크포인트는 변경하지 않는다.
