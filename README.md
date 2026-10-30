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
| 보호자 승인 후 음악 명령 → **이 PC 스피커로 재생**(`-Speaker`, 임시곡으로 확인. 켜지 않으면 가상 장치) | GPIO 등 별도 스피커 장치 |

모델 점수는 "개 짖음 소리 **후보**"이며 감정·질환·원인을 판정하지 않습니다. 5초 창은 정확한 발성 시작·종료가 아닙니다.

## 한 번에 실행하기 (Windows 노트북)

**새 PC에서 준비** (PowerShell, 한 번만):

```powershell
winget install Python.Python.3.12 Git.Git Google.Chrome         # Python 3.12로 시험했습니다
git clone https://github.com/flutter/flutter.git -b 3.32.4 $env:USERPROFILE\flutter   # Flutter 3.32.x; PATH에 넣거나 FLUTTER_HOME을 설정
git clone https://github.com/wuerphe39/capstone_really.git ; cd capstone_really
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-runtime.txt       # 백엔드·수집·FFmpeg
py -3.12 -m pip install -r requirements-yamnet-experiment.txt                  # YAMNet(TensorFlow, 약 0.5GB). 별도 venv를 쓰려면 아래 참고
```

(위 `winget`·Flutter 설치 명령은 이 노트북에서 실행해 보지 않았습니다. 이미 도구가 설치된 노트북의 새 clone·새 가상환경에서 시험했습니다.)

Windows는 기본적으로 `.ps1` 실행을 막으므로 **`scripts\start_demo.cmd`**(실행 정책을 바꾸지 않고 PowerShell 스크립트를 실행)를 쓰세요. 빠진 준비물이 있으면 시작 전에 한꺼번에 알려 주고 아무것도 켜거나 끄지 않습니다. 마이크·웹캠을 쓰려면 Windows 설정 → 개인 정보 보호에서 마이크·카메라 접근을 허용합니다.

```powershell
.\scripts\start_demo.cmd -Seed            # 처음: 웹 빌드 → 서비스 시작 → 공개 음원으로 시연 데이터 → 브라우저
.\scripts\start_demo.cmd -Capture         # 웹캠·마이크 수집까지 켜기(데이터 유지)
.\scripts\start_demo.cmd -Rebuild         # petmind_app/lib을 고친 뒤 웹 다시 빌드
.\scripts\start_demo.cmd -Gemini          # 설명을 Gemini로(.env의 GEMINI_API_KEY 필요, 파생 문장만 전송, 음원·영상은 보내지 않음)
.\scripts\start_demo.cmd -Stop            # 모두 끄기
```

TensorFlow를 시스템 Python 대신 별도 가상환경에 설치했다면 `$env:PETMIND_YAMNET_PYTHON = "C:\경로\.tfvenv\Scripts\python.exe"`로 지정합니다(기본은 `py -3.12`). 새 PC 설치 시험 결과는 [docs/STATUS.md](docs/STATUS.md)를 참고하세요.

화면은 http://localhost:8021/ 입니다. 화면에서 **외출·음원 → 자동 관찰**로 외출을 시작하면 수집 에이전트가 노트북 웹캠·마이크로 수집을 시작합니다. 데이터는 `artifacts/demo/`(Git 제외)에 저장되고, 외부로 나가는 요청은 없으며 설명 제공자는 규칙 방식입니다. 시연 데이터는 실제 반려견 기록이 아니라 공개 음원(ESC-50)과 시연 담당자 의견입니다.

- **인터넷 없이도 화면이 정상으로 뜹니다.** 한글·영문 글꼴(Noto Sans KR, SIL OFL)을 앱에 포함했습니다. 포함하기 전에는 외부 주소(`fonts.gstatic.com`)만 막아도 글자가 전부 사라졌습니다. 외부 요청 0건, Chrome·Edge, 1024×768~1920×1080에서 확인했습니다.
- 웹 빌드는 한글 경로에서 실패하므로 `C:\petmind_build`에서 자동으로 합니다(`PETMIND_BUILD_ROOT`로 변경). 서비스 워커 캐시를 끄고 빌드하므로 다시 빌드해도 옛 화면이 남지 않습니다.
- 카메라·마이크는 `scripts/make_capture_input.py`가 자동 선택합니다. 다른 마이크를 쓰려면 `python -m scripts.make_capture_input --audio <이름 일부>`.
- 서비스 구성: YAMNet 분석 서비스 `8030`, 백엔드 `8010`(기본은 이 PC 전용, `-Lan`이면 같은 네트워크의 폰·PC도 접속 가능), 웹 `8021`, 카메라 미리보기 `18081`(로컬).

## 폰·다른 PC에서 보기 (같은 네트워크)

보호자가 폰으로 확인하는 것이 이 프로젝트의 쓰임입니다. 기본 실행은 보안을 위해 **이 PC에서만** 열리고, 다른 기기에서 쓰려면 `-Lan`으로 켭니다.

```powershell
.\scripts\start_demo.cmd -Lan -Capture      # 접속 주소와 QR 코드가 나옵니다
```

1. 폰을 **PC와 같은 와이파이**에 연결하고, 화면에 뜬 **QR 코드를 폰 카메라로 스캔**합니다(또는 터미널에 나온 `http://PC주소:8010/?key=…` 주소를 엽니다).
2. 처음 한 번만 키가 필요합니다. 폰 브라우저가 기억하고, 주소에서는 키가 지워집니다. 그다음부터는 `http://PC주소:8010/`만 열면 됩니다.
3. 폰에서도 외출 시작·종료, 원본 확인, 의견, 설명, 카메라 보기를 할 수 있습니다. 수집은 계속 PC의 마이크·웹캠이 합니다.

- **보호 방식**: 접속 키가 있는 기기만, 그것도 같은 사설망(집·사무실 와이파이)의 기기만 허용합니다. 공인 IP는 키가 있어도 거절하고, 키를 10번 틀리면 1분간 잠기고, 다른 사이트에서 오는 요청도 막습니다. 키는 `artifacts/demo/lan-key.txt`(Git 제외)에 있고 지우면 새로 만들어집니다.
- **집 밖에서 보기(Tailscale VPN)**: PC와 폰에 [Tailscale](https://tailscale.com/download)을 설치하고 같은 계정으로 로그인하면, `-Lan`으로 켤 때 **Tailscale 주소(`100.x`)가 맨 위에 나오고 QR도 그 주소**로 만들어집니다. 이 주소는 집 와이파이에서도, 모바일 데이터로 밖에 있을 때도 똑같이 열리고 통신이 암호화됩니다. 외출 중에는 PC가 켜져 있고(절전·잠금 해제 방지) `-Lan -Capture`로 돌고 있어야 합니다.
- **카메라 화면은 접속자에 따라 자동으로 바뀝니다.** 이 PC에서는 30fps 연속 스트림(약 4.7 Mbit/s)이고, 폰 등 원격 접속자에게는 **작은 화면을 받아 오는 저대역 보기**(360px에서 시작해 최대 480px, 장당 약 10 KB, 응답 시간에 맞춰 동시 요청 1~4장, 초당 약 16장)입니다. 모바일 망을 흉내 낸 환경(2 Mbit/s)에서 한 번에 한 장씩 받던 방식은 초당 6장·간격 172 ms(왕복 80 ms)였고, 지금 방식은 왕복 80 ms에서 초당 16.1장·간격 63 ms, 왕복 150 ms에서도 초당 15.8장·간격 63 ms였습니다. 초당 약 16장 × 약 10 KB는 대략 1.4 Mbit/s(분당 약 10 MB)이므로 모바일 데이터 사용량에 유의하세요. 화면 아래 줄에 현재 초당 장수와 응답 시간이 표시됩니다. 모바일 데이터에서 연속 스트림은 망이 흔들릴 때 밀린 영상이 쌓여 지연이 수 초로 커지는데, 한 장씩 받으면 지연이 쌓이지 않고 장수만 줄어듭니다. 응답이 느리면 화질을 낮추고 빠르면 올립니다. 원격 접속자에게는 연속 스트림을 아예 제공하지 않습니다(PC 자신에서만 두 보기를 오갈 수 있습니다).
- **터널은 지원하지 않습니다**: Cloudflare Tunnel, ngrok, 리버스 프록시처럼 PC 안에서 접속을 전달하는 방식은 `X-Forwarded-For` 같은 헤더가 붙은 요청을 서버가 **거절**합니다(PC 자신처럼 보여 키 검사를 건너뛰는 것을 막기 위해). Tailscale은 이런 헤더 없이 직접 연결됩니다.
- **한계**: 주소가 `http`라서(같은 네트워크 안에서는) 암호화되지 않습니다. Tailscale 주소로 쓰면 VPN이 암호화합니다. 집 와이파이나 개인 핫스팟에서만 쓰고, **공용 와이파이에서는 켜지 마세요.** 주소를 아는 사람은 녹음·영상을 볼 수 있으니 공유하지 마세요.
- **연결이 안 될 때**: 학교·행사장 와이파이(eduroam 등)는 기기끼리의 통신을 막는 경우가 많습니다. 이때는 **폰 핫스팟을 켜고 PC를 거기에 연결**하면 됩니다. Windows 방화벽이 막으면 시작 창의 안내 명령을 관리자 PowerShell에서 한 번 실행하세요.
- **짖음이 이어지면 알림**: 외출 중 수집 프로그램이 올린 5초 구간에서 개 짖음 후보가 **30초 동안 이어지면**(6개 구간 중 5개 이상이고 가장 최근 구간도 후보) 웹 화면 맨 위에 경고 띠가 뜨고, "잔잔한 음악" 제안이 승인 대기 상태로 만들어집니다. 5분 안에는 같은 외출에서 다시 알리지 않습니다. 승인하기 전에는 아무 소리도 재생되지 않고, 승인해도 지금은 가상 장치입니다. 폰 알림은 `.\scripts\start_demo.cmd -Gemini -Lan -Capture -Notify`로 켭니다. 시작 창에 나오는 **주제 이름**을 폰의 [ntfy 앱](https://ntfy.sh)에서 "주제 구독"에 넣으면 됩니다(주제 이름이 곧 비밀번호이니 공유하지 마세요). 외부 서비스(ntfy.sh)로 나가는 것은 "짖음 후보가 약 30초 이어졌습니다" 같은 짧은 문장과 앱 주소(Tailscale 주소)뿐이며 음원·영상·접속 키는 나가지 않습니다. `-Notify` 없이는 외부로 아무것도 나가지 않고 웹 화면의 경고 띠만 뜹니다. 이 기능은 짖음의 원인이나 감정을 판단하지 않으며, 알림을 받은 보호자가 원본을 듣고 판단합니다.
- **음악 실제 재생(`-Speaker`)**: `.\scripts\start_demo.cmd -Gemini -Lan -Capture -Notify -Speaker`로 켜면, 보호자가 승인한 "잔잔한 음악"이 **이 PC의 스피커로 실제 재생**됩니다(최대 60초, 승인할 때마다 한 번). 이 옵션이 없으면 음악 명령은 가상 실행입니다. 음악은 보호자가 `artifacts/music/reggae/`와 `artifacts/music/soft_rock/` 폴더에 넣은 곡(WAV·MP3·FLAC·M4A·OGG)을 **승인할 때마다 장르를 번갈아 다음 곡으로** 재생합니다(보호소 개 38마리 연구에서 레게와 소프트록의 스트레스 지표가 가장 좋았지만 짖음 감소는 확인되지 않았고, 한 곡만 반복하면 익숙해진다는 결과도 있습니다. 집에 혼자 있는 반려견에게 같은 효과가 있는지는 확인되지 않았습니다). 모든 곡은 조용한 크기로 맞추고 8초에 걸쳐 서서히 줄입니다(음악이 갑자기 끊기면 짖음이 늘었다는 연구가 있습니다). 시연용으로 자유 이용(CC BY 4.0) 곡 6곡(Kevin MacLeod, 레게 3·부드러운 기타 위주 록 3)을 넣어 두었습니다. 출처·해시·**영상에 넣을 때 필요한 표기 문구**는 [docs/MUSIC_CREDITS.md](docs/MUSIC_CREDITS.md)에 있습니다. 다른 곡을 쓰려면 직접 구해 넣으세요(저작권이 있는 곡은 이 저장소에 올리지 마세요. `artifacts/`는 Git이 무시합니다). 폴더가 비어 있으면 임시로 조용한 곡을 PC에서 직접 만들어 쓰는데, 이것은 실제 노래가 아닌 자리표시용입니다. 소리 크기는 PC 볼륨을 따르므로 시연 전에 확인하세요. 곡은 기본으로 -34 LUFS까지 낮춰 재생하며(처음 버전 -28보다 6 dB, 진폭의 절반), 더 줄이거나 키우려면 서버를 켜기 전에 PowerShell에서 `$env:PETMIND_MUSIC_LUFS='-44'`처럼 숫자를 정하세요(-50~-14, 작을수록 조용). 승인 전에는 아무 소리도 나지 않고, 화면의 승인 버튼과 기록에는 "PC 스피커 음악 재생"으로 표시됩니다. 음악이 짖음에 효과가 있다는 근거는 아직 없으며, 전후 변화를 기록할 뿐 인과를 판단하지 않습니다.

## 동작 흐름

```text
마이크·웹캠 ─ FFmpeg ─ 5초 구간 ─▶ YAMNet Bark 점수 ─▶ 기록(SQLite) ─▶ 보호자 확인(의견)
                  │                      │                                   │
                  │                      └ 감지 구간 ±5초 사건 영상 ◀────────┤
                  └ 카메라 미리보기(MJPEG, 메모리에만)                       ▼
                                          외출·귀가 요약 ◀─ 개별 기록 RAG(MCP 검색 → 근거 ID 인용 설명)
                                                                             │
                                                    보호자 승인 후 음악 명령 → PC 스피커 재생(-Speaker) 또는 가상 장치
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
| 음성 모델 | 임계값 0.05 고정. **ESC-50 2,000클립: 개 40/40, 오탐 1.7%.** **FSD50K 가정 소음 680클립: 짖음 40/49, 오탐 1.4%(말소리 1/80, 초인종·노크·전화·알람·음악 0, 울음 4/28, 고양이 3/60).** AudioSet 구간 평가 F1 0.816(106창) | ESC-50 짖음은 또렷해 재현율이 낙관적. FSD50K에서 놓친 9개는 긴 클립 속의 약한 짖음. 1초 미만 짖음은 AudioSet 평가에서 다수 놓침(FSD50K에는 3초 미만 클립이 6개뿐). 울음·고양이·수탉·돼지 같은 비슷한 음색 오탐. 실제 강아지 미평가 ([ESC-50](docs/YAMNET_ESC50_EVAL.md), [FSD50K 가정 소음](docs/YAMNET_FSD50K_HOUSEHOLD_EVAL.md), [docs/47](docs/47_AudioSet_시간구간_짖음_평가.md)) |
| 보관·삭제 | 원본·사건 영상 보관 기간 만료 삭제, 삭제·학습 철회 (자동 시험) | 7일 경과 실기 확인 |
| 화면 | Flutter 웹: 외출·음원, RAG·케어, 기록, 설정·시연 | |
| 설명 | 규칙 제공자(기본)와 Gemini(`start_demo.cmd -Gemini`, `.env`의 키)로 근거 ID 인용 설명. **Gemini 실호출 확인: 귀가 설명 3/3, 앱 수준 3/3, 폴백 없음** | 합성·공개 음원 시연 자료로만 확인. 케어 제안 문장의 사실성은 독립 평가 아님. 무료 구간 입력은 Google 제품 개선에 쓰일 수 있음 ([docs/GEMINI_REAL_CALL_CHECK.md](docs/GEMINI_REAL_CALL_CHECK.md)) |
| 테스트 | Python **205 passed, 10 skipped**(torch 없으면 학습용 건너뜀), Flutter **30 passed**, `flutter analyze` 문제 없음 | |

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

1. **독립 평가 보완**: ESC-50 전체와 FSD50K 가정 소음 평가는 완료. 1초 미만 짖음은 표본이 부족하고, 실제 반려견 소리(시연은 사용자 강아지로 촬영 예정, 예행연습 필요)는 아직 없음.
2. 장시간 운용과 물리적 장치 분리 시험.
3. (완료) Gemini 실제 호출 확인.
4. 외부 사용자 모집 전: 사용자 계정·접근 제어. 지금의 접속 키는 기기 하나하나를 구분하지 않는 **공유 키**이며, 같은 네트워크 안에서만 쓰는 시제품용이다(`pet_id`도 인증이 아니다). 집 밖(모바일 데이터)에서 보려면 VPN(예: Tailscale) 같은 별도 방법이 필요하다.

## 문서

- 현재 상태: [docs/STATUS.md](docs/STATUS.md), [VSCODE_HANDOFF.md](VSCODE_HANDOFF.md)
- 수집: [docs/AUTOMATIC_OUTING.md](docs/AUTOMATIC_OUTING.md), [docs/CAPTURE_STABILITY.md](docs/CAPTURE_STABILITY.md)
- 음성 모델 비교: [YAMNet·LSTM 비교](docs/45_YAMNet_임베딩_LSTM_비교.md), [AudioSet 구간 평가](docs/47_AudioSet_시간구간_짖음_평가.md)
- RAG: [검증과 개선](docs/RAG_검증과_개선_2026-10-12.md), [기간·의미 검색](docs/24_RAG_기간_의미검색_개선.md)
- 발표: [발표자료/](발표자료/README.md), [docs/presentation/](docs/presentation/)
- **이전 README 전체(설치 절차·블록도 설명·검증 표·문제 해결)**: [docs/README_상세기록_2026-10-22.md](docs/README_상세기록_2026-10-22.md) — 일부는 LSTM을 운영 모델로 쓰던 시절 기준입니다.

> 문서와 실행 결과가 다르면 실제 코드와 재현된 결과를 기준으로 고칩니다.
