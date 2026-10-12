# PetMind 작업 지침

이 저장소의 **활성 프로젝트는 루트의 `pet_monitor/`, `petmind/`, `petmind_app/`, `scripts/`, `docs/`**이다. [README.md](README.md)는 실행 안내, [docs/STATUS.md](docs/STATUS.md)는 검증된 현재 상태, [VSCODE_HANDOFF.md](VSCODE_HANDOFF.md)는 후속 작업 인계다.

- 급식기는 현재 졸업작품 범위에서 제외한다. 이전 급식·센서·YouTube 시제품은 `legacy/2026-09-prototype/`에 보관한다. 활성 경로에 조용히 다시 연결하지 않는다.
- 현재 개발·발표의 핵심은 음성 LSTM과 개별 기록 RAG다. 영상 LSTM·탐지·추적 기반 자동 행동 분류는 범위에서 제외한다. 기존 영상 실험 코드는 재현용으로 보존하며 활성 기능에 다시 연결하지 않는다. 카메라는 음성 감지 창 전후의 원본 장면 확인용이다. 최근 영상 버퍼·감지 구간 저장·관찰 연결은 scripts/monitor_audio_events.py와 event-videos API에 구현되어 파일 입력 검증을 통과했다. 실제 Pi 장치·시계 오차·장시간 운용은 아직 미검증이므로 완료로 표시하지 않는다.
- 모델 결과는 합성 성적, 박스 탐지, 추적 coverage, 행동 분류 정확도를 분리해 기록한다. `unknown`을 임의 행동으로 바꾸지 않는다.
- `.env`, API 키, 개인 DB, 원본 영상·음성, 공개 데이터 원본, 모델 체크포인트, 빌드 결과는 Git에 넣지 않는다. 연구 데이터의 출처·라이선스·해시 및 집계 결과는 `docs/`에 기록한다.
- 물리 GPIO·음악 재생은 사용자가 명시적으로 장비 테스트를 요청한 경우에만 수행한다. 기본 장치는 가상 실행이다.
- 변경 뒤 해당 기능 테스트와 전체 Python 회귀 테스트를 실행한다. 필요 시 `flutter analyze`, `flutter test`, 웹 빌드를 수행하고 실제 실행한 결과만 문서에 적는다.

Windows 새 환경에서 루트 기준:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-vision.txt
.\.venv\Scripts\python.exe -m pytest tests petmind\backend\tests -q -p no:cacheprovider
```

`legacy/`는 2026년 9월의 이전 시제품 보관용이며 현재 테스트·시연·API 계약의 기준이 아니다. 보관 목적의 과거 지침은 `legacy/2026-09-prototype/AGENTS.md`에 남겨 두었다.
