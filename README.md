# PetMind

반려견의 소리를 기록하고, 보호자가 확인하고, **그 반려견의 과거 기록**으로 설명하는 시스템입니다. 소리·영상 입력은 노트북 하나의 마이크·웹캠이고, 음성 감지는 YAMNet, 설명은 개별 기록 RAG가 맡습니다. 전체 흐름은 아래 애니메이션으로 볼 수 있습니다.

![PetMind 동작 흐름 애니메이션](PetMind_동작_애니메이션.svg)

재생·단계 이동이 되는 버전은 [PetMind_동작_애니메이션.html](PetMind_동작_애니메이션.html)입니다(내려받아 브라우저에서 열기. GitHub 파일 화면에서는 스크립트가 실행되지 않습니다).

## 범위

| 하는 것 | 하지 않는 것 |
|---|---|
| 노트북 마이크·웹캠 수집(FFmpeg), 5초 구간 단위 YAMNet Bark 감지 | 별도 수집 장치(소리·영상 입력은 이 노트북 하나) |
| 감지 구간 앞뒤 5초 사건 영상 저장 — **카메라는 원본 장면 확인용** | 영상 LSTM·탐지·추적 기반 자동 행동 분류 (이전 실험 코드는 재현용으로만 보존) |
| 보호자 확인(의견), 외출·귀가 요약, 같은 반려견의 과거 기록 RAG 설명 | 급식기·센서 (`legacy/`에 보관) |
| 보호자 승인 후 음악 **명령 요청**(가상 장치로 왕복 확인) | 실제 스피커·GPIO 재생 |

모델 점수는 "개 짖음 소리 **후보**"이며 감정·질환·원인을 판정하지 않습니다. 5초 창은 정확한 발성 시작·종료가 아닙니다.

## 한 번에 실행하기 (Windows 노트북)

준비: Python 3.12, Flutter 3.32.x, 마이크·웹캠 권한(Windows 개인정보 설정).

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-runtime.txt        # 백엔드·수집·FFmpeg
py -3.12 -m pip install -r requirements-yamnet-experiment.txt                  # YAMNet(TensorFlow)

.\scripts\start_demo.ps1 -Seed            # 처음: 웹 빌드 → 서비스 시작 → 공개 음원으로 시연 데이터 → 브라우저
.\scripts\start_demo.ps1 -Capture         # 웹캠·마이크 수집까지 켜기(데이터 유지)
.\scripts\start_demo.ps1 -Rebuild         # petmind_app/lib을 고친 뒤 웹 다시 빌드
.\scripts\start_demo.ps1 -Stop            # 모두 끄기
```

화면은 http://localhost:8021/ 입니다. 화면에서 **외출·음원 → 자동 관찰**로 외출을 시작하면 수집 에이전트가 노트북 웹캠·마이크로 수집을 시작합니다. 데이터는 `artifacts/demo/`(Git 제외)에 저장되고, 외부로 나가는 요청은 없으며 설명 제공자는 규칙 방식입니다. 시연 데이터는 실제 반려견 기록이 아니라 공개 음원(ESC-50)과 시연 담당자 의견입니다.

- 웹 빌드는 한글 경로에서 실패하므로 `C:\petmind_build`에서 자동으로 합니다(`PETMIND_BUILD_ROOT`로 변경). 서비스 워커 캐시를 끄고 빌드하므로 다시 빌드해도 옛 화면이 남지 않습니다.
- 카메라·마이크는 `scripts/make_capture_input.py`가 자동 선택합니다. 다른 마이크를 쓰려면 `python -m scripts.make_capture_input --audio <이름 일부>`.
- 서비스 구성: YAMNet 분석 서비스 `8030`, 백엔드 `8010`(로컬 전용), 웹 `8021`, 카메라 미리보기 `18081`(로컬).

## 동작 흐름

```text
마이크·웹캠 ─ FFmpeg ─ 5초 구간 ─▶ YAMNet Bark 점수 ─▶ 기록(SQLite) ─▶ 보호자 확인(의견)
                  │                      │                                   │
                  │                      └ 감지 구간 ±5초 사건 영상 ◀────────┤
                  └ 카메라 미리보기(MJPEG, 메모리에만)                       ▼
                                          외출·귀가 요약 ◀─ 개별 기록 RAG(MCP 검색 → 근거 ID 인용 설명)
                                                                             │
                                                    보호자 승인 후 음악 명령 요청(가상 장치)
```

- **수집**: `scripts/capture_agent.py`가 화면의 자동 관찰 요청을 가져와 `scripts/monitor_audio_events.py`를 실행합니다.
- **감지**: `petmind/yamnet_service/`(포트 8030). 기본 detector는 `yamnet`(`PETMIND_AUDIO_DETECTOR`), 임계값 0.05. 이전 log-mel LSTM은 `lstm`으로 켜는 비교 기준으로만 남아 있습니다.
- **RAG**: 같은 반려견·과거 기록만 시간으로 제한해 MCP로 검색하고, 서버가 집계한 사실에서 근거 ID를 골라 설명합니다. 키가 없으면 규칙 제공자입니다(`GEMINI_API_KEY`는 로컬 `.env`에만).
- **미관찰 시간**: 분석하지 못한 시간은 "조용했던 시간"이 아니라 관찰 공백으로 표시합니다.

## 현재 상태 (2026-10-23)

| 항목 | 확인한 것 | 아직 아닌 것 |
|---|---|---|
| 수집 → 분석 → 저장 | 노트북 웹캠·마이크로 5초 구간 분석·저장. **노트북 스피커로 튼 개 짖음을 내장 마이크가 받아 감지, 감지 구간의 사건 영상(H.264+AAC 35초) 저장 확인**, 소리 없는 구간·빗소리 오탐 없음 | 공개 음원 4개를 되녹음한 기능 확인(실제 반려견 아님, 약한 클립 1개는 놓침). [docs/LIVE_BARK_TEST.md](docs/LIVE_BARK_TEST.md) |
| 카메라 미리보기 | 640×480 MJPEG, 브라우저 수신 평균 **29.9fps**(22초) | 장시간 |
| 수집 안정성 | 10분 수집 중 FFmpeg 2회 강제 종료 → 자동 재시작, 메모리·임시 디스크 증가 없음. 장치 재탐지, 백엔드 일시 단절 허용 | 수 시간 운용, 장치를 물리적으로 뽑았다 꽂기. [docs/CAPTURE_STABILITY.md](docs/CAPTURE_STABILITY.md) |
| 음성 모델 | **ESC-50 전체 2,000클립, 임계값 0.05 고정: 개 짖음 40/40 감지, 오탐 34/1,960(1.7%; 사람·가전 소음 0.9%, 다른 동물 6.7%).** AudioSet 구간 평가 F1 0.816(106창) | ESC-50 짖음은 또렷해 재현율이 낙관적. 1초 미만 짖음은 AudioSet 평가에서 다수 놓침, 다른 동물 소리 오탐. TV·말소리·초인종·실제 강아지는 미평가 ([ESC-50 평가](docs/YAMNET_ESC50_EVAL.md), [docs/47](docs/47_AudioSet_시간구간_짖음_평가.md)) |
| 보관·삭제 | 원본·사건 영상 보관 기간 만료 삭제, 삭제·학습 철회 (자동 시험) | 7일 경과 실기 확인 |
| 화면 | Flutter 웹: 외출·음원, RAG·케어, 기록, 설정·시연 | |
| 설명 | 규칙 제공자로 근거 ID 인용 설명 | Gemini 실제 호출은 이 노트북에서 재확인 안 함 (이전 기록: [docs/evidence/rag_v2_real_integration.json](docs/evidence/rag_v2_real_integration.json)) |
| 테스트 | Python **197 passed, 10 skipped**(torch 없으면 학습용 건너뜀), Flutter **27 passed**, `flutter analyze` 문제 없음 | |

실제 반려견·가정 환경 정확도, 개체·감정·질환 판정, 음악의 케어 효과는 검증하지 않았고 주장하지 않습니다.

## 저장소 구조

```text
petmind/
  backend/            FastAPI·SQLite·MCP 검색·설명 제공자(규칙/Gemini)·수집 작업 API
  yamnet_service/     YAMNet 분석 서비스(8030)
  device_agent.py     가상 음악 장치
petmind_app/          Flutter 보호자 화면(웹)
scripts/              start_demo.ps1, 수집(monitor_audio_events·capture_agent·make_capture_input·preview_stream), 시연 데이터, 평가
pet_monitor/          음성 분석 코드와 보존된 이전 영상 실험
tests/                Python 회귀 테스트
docs/                 현재 상태(STATUS.md)·검증 기록·발표 자료·상세 기록
발표자료/ 제출문서/    발표 영상·대본 / 계획서·지도계획서(Git에는 올리지 않는 서식 포함)
experimental/         비교 시험 사이트
legacy/               이전 급식·센서·YouTube 시제품(현재 실행 경로 아님)
```

Git에 넣지 않는 것: `.env`, API 키, 개인 DB, 원본 음성·영상, 공개 데이터 원본, 모델 체크포인트, 빌드 결과(`artifacts/` 등).

## 설정

| 설정 | 기본 | 의미 |
|---|---|---|
| `PETMIND_AUDIO_DETECTOR` | `yamnet` | 음성 감지기(`lstm`은 비교용) |
| `PETMIND_YAMNET_URL` | `http://127.0.0.1:8030/analyze` | YAMNet 서비스 주소 |
| `PETMIND_LLM_PROVIDER` | 키 있으면 `gemini`, 없으면 `rule` | 설명 제공자 |
| `GEMINI_API_KEY` | 빈 값 | 로컬 `.env`에만 입력 |
| `PETMIND_SEMANTIC_SEARCH` | `off` | 임베딩 의미 검색 |
| `PETMIND_DATABASE_URL` / `PETMIND_AUDIO_STORAGE_DIR` | 루트 `petmind.db` / 저장소 내 폴더 | 기록·음원 위치(데모는 `artifacts/demo/`) |
| `PETMIND_CAMERA_SNAPSHOT_URL` | 비어 있음 | 카메라 미리보기 원본(`-Capture`가 설정) |

전체 목록은 [petmind/backend/settings.py](petmind/backend/settings.py)와 `.env.example`을 따릅니다.

## 테스트

```powershell
.\.venv\Scripts\python.exe -m pytest tests petmind\backend\tests -q -p no:cacheprovider
cd petmind_app; flutter analyze; flutter test
```

## 남은 일

1. **독립 평가 보완**: ESC-50 전체 평가는 완료. TV·말소리·초인종 같은 가정 소음과 짧은 짖음 자료, 그리고 실제 반려견 소리(시연은 사용자 강아지로 촬영 예정, 예행연습 필요)는 아직 없음.
2. 장시간 운용과 물리적 장치 분리 시험.
3. Gemini 실제 호출 재확인(키 필요).
4. 외부 사용자 모집 전: 사용자 인증·접근 제어(현재 `pet_id`는 인증이 아니며 로컬 단일 가정 시제품).

## 문서

- 현재 상태: [docs/STATUS.md](docs/STATUS.md), [VSCODE_HANDOFF.md](VSCODE_HANDOFF.md)
- 수집: [docs/AUTOMATIC_OUTING.md](docs/AUTOMATIC_OUTING.md), [docs/CAPTURE_STABILITY.md](docs/CAPTURE_STABILITY.md)
- 음성 모델 비교: [YAMNet·LSTM 비교](docs/45_YAMNet_임베딩_LSTM_비교.md), [AudioSet 구간 평가](docs/47_AudioSet_시간구간_짖음_평가.md)
- RAG: [검증과 개선](docs/RAG_검증과_개선_2026-10-12.md), [기간·의미 검색](docs/24_RAG_기간_의미검색_개선.md)
- 발표: [발표자료/](발표자료/README.md), [docs/presentation/](docs/presentation/)
- **이전 README 전체(설치 절차·블록도 설명·검증 표·문제 해결)**: [docs/README_상세기록_2026-10-22.md](docs/README_상세기록_2026-10-22.md) — 일부는 LSTM을 운영 모델로 쓰던 시절 기준입니다.

> 문서와 실행 결과가 다르면 실제 코드와 재현된 결과를 기준으로 고칩니다.
