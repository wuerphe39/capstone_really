# PetMind 작업 인계

기준일: 2026-10-23. 이 문서는 새로 시작하는 사람(또는 새 세션)이 바로 이어서 일하도록 현재 상태만 적는다. 2026-10-11 이전 인계 내용은 git 이력과 `docs/01_*`~`docs/48_*`에 남아 있다.

먼저 읽을 것: [AGENTS.md](AGENTS.md)(작업 원칙), [README.md](README.md)(실행·현황), [docs/STATUS.md](docs/STATUS.md)(확인한 것/못 한 것).

## 지금 구성

노트북 하나. 마이크·웹캠(FFmpeg) → 5초 구간 → YAMNet Bark(임계값 0.05) → SQLite → 보호자 확인 → 개별 기록 RAG 설명 → 승인형 음악 명령(가상). Raspberry Pi·영상 행동 분류·급식기는 범위 밖이다(`legacy/`와 일부 `docs/NN_*`는 보존용).

```powershell
.\scripts\start_demo.cmd -Seed      # 처음: 웹 빌드·서비스 시작·공개 음원 시연 데이터
.\scripts\start_demo.cmd -Capture   # 웹캠·마이크 수집까지(화면에서 '자동 관찰'로 외출 시작)
.\scripts\start_demo.cmd -Stop
.\.venv\Scripts\python.exe -m pytest tests petmind\backend\tests -q -p no:cacheprovider
cd petmind_app; flutter analyze; flutter test
```

환경: `.venv`(Python 3.12, `requirements-runtime.txt`), TensorFlow가 있는 `py -3.12`(YAMNet, `requirements-yamnet-experiment.txt`), Flutter 3.32.x. 한글 경로에서는 `flutter build web`이 실패하므로 런처가 `C:\petmind_build`에서 빌드한다.

## 코드 지도

| 위치 | 역할 |
|---|---|
| `scripts/capture_agent.py` | 화면의 자동 관찰 요청을 가져와 수집 프로그램을 실행·감시(재시작 5회, 장치 재탐지, 백엔드 단절 허용) |
| `scripts/monitor_audio_events.py` | FFmpeg로 웹캠·마이크를 5초씩 수집, 업로드, 감지 구간 ±5초 사건 영상, 카메라 미리보기 |
| `scripts/make_capture_input.py`, `preview_stream.py` | 장치 자동 선택(640×480 MJPEG 30fps), MJPEG 스트림 |
| `petmind/yamnet_service/` | YAMNet 분석 서비스(8030) |
| `petmind/backend/` | FastAPI·SQLite·MCP 검색·설명 제공자(규칙/Gemini)·수집 작업 API |
| `petmind_app/` | Flutter 보호자 화면(웹) |
| `scripts/live_bark_check.py`, `evaluate_yamnet_esc50.py` | 실제 소리 시험, ESC-50 전체 평가 |

## 이어서 할 일 (우선순위)

1. **실제 강아지로 예행연습**: 시연 영상은 사용자 강아지로 촬영한다. 같은 방에서 30~60초 수집해 점수·마이크 위치·"오디오 개선 사항"(스피커 재생 시험 때문에 현재 꺼 둠) 설정을 비교한다. 다른 동물 소리(TV 등)가 나오지 않게 한다.
2. 평가 보완: 1초 미만 짖음 자료(표본이 부족함). 가정 소음은 ESC-50·FSD50K로 평가했다([ESC-50](docs/YAMNET_ESC50_EVAL.md), [FSD50K](docs/YAMNET_FSD50K_HOUSEHOLD_EVAL.md)).
3. **진짜 다른 PC에서의 설치 검증**: 이 노트북에서는 새 clone·새 venv·분리된 TensorFlow venv·실행 정책·누락 점검까지 시험했다([docs/STATUS.md](docs/STATUS.md)). Python·Git·Flutter가 없는 PC에서 README의 "새 PC에서 준비" 명령(`winget`, Flutter clone)이 되는지는 아직 시험하지 못했다.
4. 장시간 운용과 장치 물리 분리 시험, Gemini 실호출(키 필요), 외부 사용자 모집 전 인증.

## 지켜야 할 것

- `.env`, API 키, 개인 DB, 원본 음성·영상, 공개 데이터 원본, 모델 체크포인트, 빌드 결과는 Git에 넣지 않는다(`artifacts/`는 제외됨). 시험 중 마이크·웹캠 녹음은 시험 뒤 삭제한다(`live_bark_check.py`는 자동 삭제).
- `제출문서/`(팀원 연락처 포함)와 로컬 설정 `.claude/`는 커밋하지 않는다. 푸시는 사용자가 요청할 때만 한다.
- 물리 GPIO·음악 재생은 사용자가 장비 테스트를 명시할 때만 한다. 기본은 가상 장치.
- 모델 점수는 "개 짖음 소리 후보"이며 감정·질환·원인을 판정하지 않는다. 확인하지 않은 것을 완료로 쓰지 않는다.

## 새 세션에 붙여넣기

> `AGENTS.md`, `README.md`, `VSCODE_HANDOFF.md`, `docs/STATUS.md`를 읽고 현재 변경을 보존한 채 이어서 진행해 줘. 위 "이어서 할 일"의 1번은 사용자(강아지)가 있어야 하므로 2~4번부터 진행하고, 실제로 실행해 확인한 것과 못 한 것을 구분해서 문서에 남겨 줘.
