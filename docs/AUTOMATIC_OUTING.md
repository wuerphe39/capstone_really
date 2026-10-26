# 외출 시작과 자동 수집·음성 분석

노트북 한 대에서 백엔드, YAMNet 서비스, 수집 에이전트가 함께 돈다. 수집 안정성 보강과 시험 결과는 [CAPTURE_STABILITY.md](CAPTURE_STABILITY.md)에 있다.

## 사용자 흐름

외출·음원 메뉴의 기본 모드는 `자동 관찰 · PC 입력`이다. 음성·사건 영상 저장에 동의하고 외출을 시작하면 DB에 수집 요청(`capture_jobs`)이 저장된다. 수집 에이전트(`scripts/capture_agent.py`)가 요청을 가져가 FFmpeg로 웹캠·마이크를 수집하는 프로그램(`scripts/monitor_audio_events.py`)을 실행한다. 음원을 직접 올릴 필요가 없다. 업로드 모드는 보조 입력으로 계속 제공한다.

서버는 요청 생성만으로 분석 중이라고 표시하지 않는다. 수집 프로그램 연결 대기 → 장치 준비 → 실제 음원 분석 완료 후 분석 중으로 바뀐다. 모델 미준비·연결 끊김도 구분한다.

- **시계 검사**: 요청 수락과 heartbeat 응답의 서버 UTC 시각을 에이전트의 요청 왕복 시각과 비교한다. 왕복 지연 또는 추정 시계 오차가 2초를 넘으면 `clock_mismatch`로 외출을 종료해 잘못된 시각의 기록을 막는다. 같은 PC에서는 오차가 거의 없어 이상 징후 감지용이다.
- **연결 끊김**: 30초간 heartbeat가 없으면 연결 끊김으로 표시한다. 단절된 작업은 다른 에이전트가 빼앗지 않는다.
- **복구**: 수집 프로그램이 비정상 종료하거나 멈추면 에이전트가 최대 5번 다시 시작하고, 장치는 시작 전마다 다시 탐지한다. 백엔드가 잠깐 끊겨도 바로 멈추지 않는다. 자세한 기준은 CAPTURE_STABILITY.md. 오프라인 재전송은 구현하지 않았다.
- **귀가**: 귀가 버튼은 먼저 중지를 요청한다. 진행 중인 작업은 FFmpeg에 종료 입력을 보내 마지막 구간을 닫고, 음원 분석과 사건 영상 저장을 마친 뒤 외출을 종료한다. 기다리는 동안 화면은 종료 처리 중으로 표시한다. 에이전트가 대기 중이거나 이미 끊긴 경우 서버에서 외출을 종료한다. 끝난 외출에 대한 후속 관찰 저장은 API 검증으로 거부된다.

## 실행

대부분은 한 명령으로 켠다(웹 빌드, 서비스, 에이전트, 장치 자동 선택).

```powershell
.\scripts\start_demo.ps1 -Capture
```

수동으로 에이전트만 실행하려면 저장소 루트에서 다음과 같이 한다. `pet-id`는 화면에서 선택한 반려견 ID와 같아야 한다.

```powershell
.\.venv\Scripts\python.exe -m scripts.make_capture_input          # 장치 자동 선택 → artifacts/demo/capture-input.json
.\.venv\Scripts\python.exe -m scripts.capture_agent --base http://127.0.0.1:8010 --pet-id demo-dog `
    --input-args-file artifacts/demo/capture-input.json --ffmpeg <ffmpeg 경로> --video-map 0:v:0 --audio-map 1:a:0 --redetect
```

카메라 미리보기를 쓰려면 백엔드에 `PETMIND_CAMERA_SNAPSHOT_URL=http://127.0.0.1:18081/snapshot.jpg`를 설정한다(`start_demo.ps1 -Capture`가 설정).

## 카메라 미리보기와 저장

수집 프로그램이 FFmpeg의 두 번째 출력(최대 30fps, 640px MJPEG)을 `127.0.0.1:18081/stream`으로 내보내고 백엔드 `/camera/stream`이 전달한다. 프레임은 메모리에만 두며 저장하지 않는다. 수집이 멈추면 스트림이 끊긴다. 외출 밖 상시 라이브는 제공하지 않는다.

음성은 기본 7일 보관, 공통 학습 동의는 false다. 자동 외출 시작 시의 저장 동의 시각은 외출 기록에 남긴다. 사건 전후 장면만 영속 저장하고 연속 영상 버퍼는 임시 폴더에 둔다(최대 128MB). RAG와 요약은 외출 전체 시간에서 분석 표본을 뺀 시간을 관찰 공백으로 설명하며, 조용했던 시간으로 간주하지 않는다.

## 관련 파일과 검증

- `database.py`, `routers/capture.py`, `routers/outings.py`, `main.py`: `capture_jobs` 테이블, 동의·소유권·중복 수신 방지·대기 취소·귀가 완료·단절.
- `scripts/capture_agent.py`, `scripts/monitor_audio_events.py`: 중지 파일, 진행 상태, 프레임 공유, heartbeat, 재시작, 프로세스 정리.
- `outings_panel.dart`, `audio_panel.dart`, `main.dart`: 기본 자동 모드, 저장 동의, 상태 갱신, 음원 의견 검토.
- `services/outings.py`: RAG 근거에 미분석 시간과 해석 제한 추가.
- 테스트: `petmind/backend/tests/test_capture.py`(수집 수명주기), `tests/test_agent_supervision.py`(재시작·장치 대기), `petmind_app/test/outings_panel_test.dart`.

API는 기본으로 비로컬 접속과 외부 웹 Origin을 거부한다. `start_demo.cmd -Lan`을 쓰면 접속 키가 있는 사설망 기기(폰 등)도 허용하지만, 사용자·기기별 인증을 구현한 것은 아니다. 외부 공개 전에는 인증과 사용자별 접근 제어가 필요하다. 작업 소유 토큰은 중복 실행 방지용이며 인증을 대체하지 않는다.
