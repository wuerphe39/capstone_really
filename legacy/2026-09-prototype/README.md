# PetMind 기반 시스템

PetMind는 카메라·마이크·센서 신호를 최근 관찰 문맥으로 합친 뒤, 케어 방법을 제안하고 보호자 승인을 받은 액션만 실행하는 캡스톤 시연 시스템이다. 목표 완료일은 **2026년 11월 7일**이다.

## 현재 진행 현황 (2026-09-28)

현재 프로젝트의 중심은 여러 모델의 정확도 비교가 아니라, 관찰 신호를 종합해 보호자에게 케어 방법을 제안하는 통합 시스템이다.

구현 완료:

- FastAPI, SQLite 기반 분석·센서·케어 제안·액션 이력 API
- `PetContext` 기반 최근 15~30초 상태 집계
- 구조화된 `CareSuggestion`과 규칙 기반 판단
- Gemini `gemini-2.5-flash-lite` 어댑터 및 오류 시 규칙 기반 폴백
- 임시 센서·행동 데이터로 LLM 피드백을 확인하는 시뮬레이터
- Flutter의 현재 상태, 판단 근거, 제공자, 음악 승인 및 실행 상태 화면
- `simulated`와 `raspberrypi` 실행 프로필을 사용하는 모듈형 edge 계층
- DHT22 어댑터, HTTP 센서 전송, 개별 센서 진단 CLI
- `simulated`/`youtube` 음악 플레이어 인터페이스
- MQTT 명령 ID와 `requested → acknowledged → completed/failed` 처리
- YouTube 영상 ID 허용 목록과 보호자 승인형 음악 재생 구조
- 급식 기능 기본 비활성화

최근 검증 결과:

- 백엔드 테스트: `10 passed`
- edge 모듈 테스트: `5 passed`
- 가상 센서에서 실행 중인 백엔드로 1회 데이터 전송 성공
- Flutter 정적 분석 및 위젯 테스트 통과

아직 필요한 작업:

- 실제 Raspberry Pi에서 DHT22 핀 연결 및 측정 검증
- Raspberry Pi 카메라를 새 edge 인터페이스에 연결
- 마이크 입력과 짖음 감지 모듈을 edge 계층에 연결
- 실제 YouTube 영상 ID 등록 및 Raspberry Pi의 `mpv`·`yt-dlp` 재생 검증
- Gemini API 키를 로컬 `.env`에 설정하고 실제 응답 확인
- 네트워크 단절 시 센서 데이터 로컬 보관 및 재전송
- 실제 장치 통합 후 응답시간·오류 복구 지표 측정

로컬 Codex에는 Eraser MCP가 OAuth 방식으로 등록되어 있다. 새 Codex 세션 또는 VS Code 창 재로딩 후 PetMind 시스템 구성도 생성에 사용할 수 있다.

## 시스템 경계

```text
AI inference agent ──POST /analysis──┐
edge sensor agent ───POST /sensors──┼─> PetContext → CareSuggestion
                                    │                  │
Flutter UI <──────── REST API ──────┘              보호자 승인
                                                       │
                                       MQTT command + command_id
                                                       │
                                        Raspberry Pi device agent
                                                       │
                                      YouTube player → completed / failed
```

`petmind/backend`는 판단과 기록, `petmind/ai`는 시각 신호 생성, `petmind/edge`는 센서·전송·음악 모듈 조립, `petmind/hardware`는 Raspberry Pi 저수준 드라이버, `petmind_app`은 보호자 UI를 담당한다. 각 프로세스는 REST 또는 MQTT로만 연결되어 개별 교체가 가능하다. 급식 관련 레거시 코드는 보존하지만 기본 실행 경로에서는 비활성화한다.

## 1. 백엔드 실행

PowerShell에서 다음 명령을 실행한다.

```powershell
.\scripts\setup_backend.ps1
.\scripts\start_backend.ps1
```

API 문서는 `http://localhost:8000/docs`, 구성 상태는 `http://localhost:8000/health`에서 확인한다. 기본값은 하드웨어 없이 안전하게 실행되는 액션 시뮬레이션 모드다.

## 2. 입력 데이터 연결

개발 PC에서 센서 모듈만 한 번 검사한다.

```powershell
.\.venv\Scripts\python.exe -m petmind.edge.cli test-sensor --profile simulated
```

가상 센서 값을 백엔드에 한 번 전송하거나 계속 전송한다.

```powershell
.\.venv\Scripts\python.exe -m petmind.edge.cli run --profile simulated --once
.\.venv\Scripts\python.exe -m petmind.edge.cli run --profile simulated
```

카메라 또는 녹화 영상의 시각 신호:

```powershell
cd petmind\ai
..\..\.venv\Scripts\python.exe inference_agent.py --source 0 --show
```

AI 전체 의존성은 별도로 `petmind/requirements.txt`를 설치해야 한다. EfficientNet 감정 모델은 기본 비활성화되며, 실험할 때만 `PETMIND_ENABLE_EMOTION=true`를 설정한다.

## 3. 통합 시나리오와 Flutter

```powershell
cd petmind
..\.venv\Scripts\python.exe simulator.py all --approve

cd ..\petmind_app
flutter run -d chrome --dart-define=PETMIND_API_BASE=http://localhost:8000
```

`--approve`는 추천 액션을 자동 승인하므로 반드시 시뮬레이션 또는 안전한 테스트 장비에서만 사용한다.

### Gemini 무료 API로 임시 데이터 피드백 확인

Google AI Studio에서 발급한 키는 코드나 Flutter에 넣지 않고 백엔드 환경변수로만 전달한다. PowerShell에서 서버를 시작하기 전에 설정한다.

```powershell
$env:PETMIND_LLM_PROVIDER="gemini"
$env:GEMINI_API_KEY="발급받은_API_키"
powershell.exe -ExecutionPolicy Bypass -File .\scripts\start_backend.ps1
```

다른 터미널에서 임시 시나리오를 전송한다.

```powershell
cd petmind
..\.venv\Scripts\python.exe simulator.py normal
..\.venv\Scripts\python.exe simulator.py anxious
```

출력의 `provider=gemini:gemini-2.5-flash-lite`를 확인한다. Flutter에서도 제공자가 `Gemini AI`로 표시된다. 키 누락, 할당량 초과, 잘못된 JSON 또는 5초 타임아웃이 발생하면 `provider=rule-fallback`으로 표시되고 기본 케어 판단을 유지한다. 무료 API에는 영상·음성 원본이나 개인정보를 보내지 않으며, 현재 구현은 익명화된 집계값만 전송한다.

## 4. Raspberry Pi 연결

Raspberry Pi OS에서 센서/통신 의존성과 시스템 패키지를 설치한다.

```bash
python -m pip install -r petmind/requirements-rpi.txt
sudo apt install python3-picamera2 mpv yt-dlp
```

Raspberry Pi의 `.env`는 다음처럼 설정한다. YouTube URL 전체가 아니라 검증한 영상 ID 11자리만 등록한다.

```env
PETMIND_EDGE_PROFILE=raspberrypi
PETMIND_DEVICE_ID=petmind-rpi-01
PETMIND_DEVICE_SIMULATE=false
PETMIND_MUSIC_PLAYER=youtube
PETMIND_YOUTUBE_CALM_PIANO_ID=
PETMIND_YOUTUBE_NATURE_SOUNDS_ID=
PETMIND_YOUTUBE_WHITE_NOISE_ID=
```

장치별 단독 확인 후 에이전트를 실행한다.

```bash
python -m petmind.edge.cli test-sensor --profile raspberrypi
python -m petmind.edge.cli run --profile raspberrypi
python -m petmind.hardware.device_agent
```

센서 구현은 네트워크 코드와 분리되어 있어 DHT22, 마이크, 추가 센서를 독립적으로 교체할 수 있다. 음악도 `simulated`와 `youtube` 플레이어가 같은 인터페이스를 사용한다. MQTT 발행만으로 성공 처리하지 않으며 Raspberry Pi의 `completed` 또는 `failed` 응답이 도착해야 상태가 확정된다.

세부 일정과 완료 기준은 [project2.md](project2.md), 구성도는 [diagram.md](diagram.md)를 기준으로 한다.
