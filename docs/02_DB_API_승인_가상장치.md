# 파트 2 — DB·API·승인·가상 장치

검증일: 2026-10-11

## 완료 내용

기존 로컬 PetMind의 DB·제안·승인·이력 구조와 제공자 인터페이스를 기준 저장소의 분석 결과에 맞춰 이식했다. 기존 분석 코드는 유지했다.

- `petmind/backend/database.py`, `schemas.py`, `settings.py`: 관찰·제안·명령 테이블과 입력 검증, 로컬 환경변수.
- `services/observations.py`: 반려견·세션·UTC 시각·입력 출처를 포함한 분석 결과 저장. 음량은 dBFS.
- `services/care.py`, `routers/care.py`: 저장된 관찰로 평가·승인·거절·명령 응답·이력 조회.
- `main.py`: 관찰 API, 합성 입력 3종, 시드 이력, 타임라인, 평가 수치, health.
- `petmind/device_agent.py`: 별도 가상 장치 프로세스가 승인된 명령을 수신·완료/실패 보고. SQLite 명령 ID 캐시로 재처리 방지.
- `scripts/start_backend.ps1`, `scripts/verify_flow.py`, `.env.example`: 실행·통합검증·설정 예제.
- 급식 API·장치는 이식하지 않았다.

## 해결한 문제

승인 전 실행하지 않는다. 승인 시 DB에 명령을 먼저 저장하고 `requested`를 반환한다. 장치 확인 후 `acknowledged`, 실행 결과 후 `completed` 또는 `failed`가 된다. 시간초과는 `timed_out`이며 늦은 응답으로 종료 상태를 되돌릴 수 없다. 중복 승인은 409, 같은 완료 응답 재전송은 같은 결과를 반환한다.

## 검증 결과

```powershell
.\.venv\Scripts\python.exe -m pytest tests petmind\backend\tests -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m uvicorn petmind.backend.main:app --host 127.0.0.1 --port 8010
.\.venv\Scripts\python.exe -m scripts.verify_flow
```

- 분석·API·MCP 합산 **29 passed**.
- 실제 HTTP 서버 health 정상.
- `calm`, `anxious`, `bored_pacing` 연속 처리: 관찰 6건(과거 시드 3 + 현재 3), 제안 3건, 승인한 가상 음악 2건 완료, 실패 0건.
- 원본 결과: `artifacts/http_flow.json`(로컬 생성, Git 제외).
- 테스트로 반려견 기록 분리, 미래 기록 제외, 중복 저장·승인, 거절, timeout, 종료 상태 보호를 확인했다.

## 남은 항목

현재 장치는 음악 재생을 모의하며 물리 스피커/GPIO를 실행하지 않는다. Pi 실행과 실제 음악은 후속 검증 대상이다. 네트워크 접근은 로컬 개발용이며 배포 인증은 아직 없다. 명령 캐시는 가상 실행의 중복 방지이며 실제 음악의 정확히 한 번 실행을 보장하는 장치 프로토콜은 아니다.
