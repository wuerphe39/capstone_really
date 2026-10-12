# 파트 32 — GitHub 저장소 정리·통합

작성일: 2026-10-11. 현재 개발 기준을 [kuro-0211/capstone](https://github.com/kuro-0211/capstone) 루트로 정리했다.

## 구조 정리

- 루트 `pet_monitor/`, `petmind/`, `petmind_app/`, `scripts/`, `docs/`는 실행·검증한 통합 PetMind를 담는다.
- 2026년 9월의 기존 시제품은 `legacy/2026-09-prototype/`에 원래 구조로 보관했다. 급식기·센서·YouTube·MQTT 실험 코드도 삭제하지 않았다. 현재 시연 경로와 혼합하지 않는다.
- 초기 분석 저장소의 당시 계획·피드백 문서와 10월 7일 통합 계획 원본은 `legacy/initial-source-docs/`에 보관했다. 이 문서들은 과거 시점의 상태이므로 현재 완료 기준으로 사용하지 않는다.
- 루트 `AGENTS.md`, `README.md`, `VSCODE_HANDOFF.md`, `docs/STATUS.md`를 현재 범위와 실행 명령 기준으로 맞췄다.
- 공개 가능한 Flutter 렌더링 캡처를 `docs/evidence/flutter_dashboard_render.png`에 배치했다. 실제 브라우저 조작·녹화 증거와 구분한다.

## 공개 범위와 재현

`.env`, API 키, 개인 DB, 공개 영상·음성 원본, 연구 데이터셋 아카이브, PyTorch/YOLO 체크포인트, 빌드·로그는 Git에서 제외했다. 해당 자산 없이도 소스와 테스트는 설치할 수 있으며 데이터·모델 준비 명령은 루트 `README.md`와 각 파트 문서에 있다. 공개 연구 자료의 라이선스·파일 해시는 `docs/evidence/`와 파트 22·27·29·30을 참고한다.

이번 정리는 기존 시제품을 지우거나 그 기능을 현재 구현으로 주장하려는 작업이 아니다. 급식기는 활성 범위에서 제외하고, Pi 실제 카메라·마이크·물리 음악, 실제 4종 행동 정확도, 장기 케어 효과는 미검증으로 유지한다.

새 저장소 위치에서 기존 개발 환경의 Python으로 테스트를 실행해 **65 passed, 1 skipped**를 확인했다. 건너뛴 1개는 Git에서 제외한 LSTM 체크포인트가 필요한 검사다. Flutter는 `analyze` 오류 없음, 기능 테스트 2개 통과, 웹 릴리스 빌드 성공이었다.
