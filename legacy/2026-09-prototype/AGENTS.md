# PetMind Codex 작업 메모

이 파일은 이후 Codex 세션이 프로젝트의 현재 상태와 중요한 결정을 빠르게 이어받기 위한 저장소 지침이다. 사용자에게 보여주는 실행 방법과 개요는 `README.md`를 함께 확인한다.

## 목표와 일정

- 프로젝트: 반려견 관찰 신호를 종합해 보호자에게 케어 방법을 제안하는 PetMind 캡스톤
- 목표 완료일: 2026-11-07
- 핵심 시연: `카메라·마이크·센서 → 상태 집계 → LLM 케어 제안 → 보호자 승인 → YouTube 음악 재생 → 결과 표시`
- 모델 정확도 경쟁보다 안정적인 전체 흐름과 근거 있는 케어 제안을 우선한다.

## 확정된 범위

- 급식 장치는 기본 시연에서 사용하지 않는다. 레거시 급식 코드는 삭제하지 않되 `PETMIND_FEATURE_FEEDING=false`를 기본으로 유지한다.
- 음악은 YouTube를 사용한다. LLM은 음악 유형만 고르고 실제 영상은 허용 목록의 11자리 영상 ID로 선택한다.
- LLM은 장치를 직접 제어하지 않는다. Flutter에서 보호자가 승인한 액션만 MQTT로 전달한다.
- Gemini가 실패하거나 키가 없거나 JSON 검증에 실패하면 규칙 기반 제공자로 자동 전환한다.
- 원본 영상·음성은 무료 LLM API로 전송하지 않는다. 집계된 `PetContext`만 전송한다.
- 개발 PC에서는 항상 시뮬레이션을 기본값으로 사용하고 실제 GPIO 모듈은 Raspberry Pi 프로필에서만 지연 로딩한다.

## 현재 구조

- `petmind/contracts`: edge와 서비스가 공유할 데이터 계약
- `petmind/edge/sensors`: 센서 인터페이스, simulated/Raspberry Pi 구현 및 팩토리
- `petmind/edge/transport`: 센서 데이터 HTTP 전송 어댑터
- `petmind/edge/players`: simulated/YouTube 음악 플레이어
- `petmind/edge/cli.py`: 센서 단독 테스트와 edge 에이전트 실행
- `petmind/hardware`: DHT22, 카메라 등 Raspberry Pi 저수준 드라이버와 호환 진입점
- `petmind/ai`: 행동 인식, 짖음 분석, 실험적 감정 모델
- `petmind/backend`: FastAPI, SQLite, 컨텍스트 집계, Gemini/규칙 제공자, MQTT 액션
- `petmind_app`: 발표용 Flutter UI
- `diagram.md`: Mermaid 시스템 구성도 원본

## 구현 상태

- 백엔드 케어 API와 이력 저장 구현됨
- Gemini 구조화 응답과 규칙 기반 폴백 구현됨
- 임시 데이터 시뮬레이터 구현됨
- Flutter 케어 제안·근거·승인·실행 상태 화면 구현됨
- 센서 인터페이스와 simulated/Raspberry Pi 프로필 구현됨
- DHT22 어댑터와 센서 진단 CLI 구현됨
- YouTube 플레이어 어댑터와 영상 ID 검증 구현됨
- MQTT 완료/실패 응답 구조 구현됨
- 실제 Raspberry Pi, 카메라, 마이크, YouTube 재생은 아직 실장 검증 전

## 안전 및 비밀값

- `.env`와 API 키를 커밋하거나 문서에 기록하지 않는다.
- `GEMINI_API_KEY`는 저장소 루트의 로컬 `.env`에서만 설정한다.
- 실제 GPIO, 음악 재생, MQTT 장치 명령은 사용자가 실제 장치 테스트를 명시하기 전까지 시뮬레이션으로 검증한다.
- `--approve`는 시뮬레이션 또는 안전한 테스트 장비에서만 사용한다.
- YouTube 플레이어는 자유 검색 결과가 아닌 환경변수에 등록한 영상 ID만 재생한다.

## 기본 실행 및 검증

저장소 루트 `C:\Users\kuro\Desktop\capstone\capstone_really`에서 실행한다.

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\start_backend.ps1
.\.venv\Scripts\python.exe -m petmind.edge.cli test-sensor --profile simulated
.\.venv\Scripts\python.exe -m petmind.edge.cli run --profile simulated --once
.\.venv\Scripts\python.exe .\petmind\simulator.py anxious
```

테스트:

```powershell
.\.venv\Scripts\python.exe -m pytest petmind\backend\tests -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m pytest petmind\edge\tests -q -p no:cacheprovider
```

마지막 검증 기준은 백엔드 `10 passed`, edge `5 passed`이다. 변경 후에는 관련 테스트를 다시 실행하고 결과를 갱신한다.

## 다음 작업 우선순위

1. Raspberry Pi 카메라와 마이크를 `petmind/edge` 인터페이스로 감싼다.
2. 센서별 `test-sensor`, 카메라 테스트, 마이크 테스트 명령을 제공한다.
3. 네트워크 실패 시 로컬 큐에 저장하고 재전송하는 기능을 추가한다.
4. 실제 Raspberry Pi에서 DHT22와 YouTube 플레이어를 검증한다.
5. 실제 Gemini 응답과 Flutter 전체 흐름을 연속 시연한다.
6. Eraser MCP로 최종 시스템 구성도를 만들고 `diagram.md`와 내용이 일치하는지 확인한다.

## 로컬 도구 상태

- Flutter SDK: `C:\Users\kuro\develop\flutter`
- Codex는 VS Code OpenAI 확장에 포함된 실행 파일을 사용한다.
- Eraser MCP 이름: `eraser`
- Eraser MCP URL: `https://app.eraser.io/api/mcp`
- Eraser 연결은 OAuth `enabled` 상태로 확인됐다. 새 세션에 도구가 없으면 VS Code 창을 다시 로드한다.
