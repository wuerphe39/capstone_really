# 파트 14 — 환경 설정과 실제 Gemini 기반 RAG 검증

검증일: 2026-10-11

## 환경 문제와 수정

사용자가 설정한 키는 `.env.example`에 있었고 실제 프로그램이 읽는 `.env`는 없었다. 설정을 Git에서 제외된 로컬 `.env`로 옮기고 예제 파일의 키는 비웠다. 키 값은 채팅·로그·문서에 출력하지 않았다.

새 설정을 읽도록 백엔드를 재시작했다. health에서 키 설정 여부 true, 제공자 gemini, 검색 모드 MCP를 확인했다. 모델은 `gemini-3.5-flash-lite`다.

## 실제 호출 중 발견한 오류

첫 실제 Gemini 응답은 등록되지 않은 recommended_actions를 반환해 Pydantic 검증에 실패했다. 단일 Literal이 JSON Schema의 `const`로 생성됐는데, Gemini의 지원 스키마 제한은 enum 방식이었다. `providers.py`에서 const를 같은 의미의 enum으로 변환했고, 액션은 music 또는 빈 배열만 허용한다는 프롬프트를 명시했다. 허용 범위를 넓히거나 잘못된 액션을 성공으로 계산하지 않았다.

`tests/test_gemini_schema.py`에서 음악만 허용하는 enum과 최대 액션 수가 유지되는 것을 검증한다.

## 실제 검증 결과

- `scripts.verify_gemini`: 실제 Gemini 제공자, MCP 검색 성공, 검색 근거의 ID 인용 확인.
- 실제 HTTP의 합성 시나리오 3종: 관찰 6건, 제안 3건, **Gemini 성공 3건·MCP 성공 3건**, 추천된 가상 음악 1건 완료, 실행 실패 0건. 음악을 추천하지 않은 시나리오에 강제로 액션을 만들지 않았다.
- 공개 음원·공개 이미지 재생 영상: 실제 Gemini 제안·MCP 검색·승인·가상 음악 완료.
- 전체 Python 테스트 **41 passed**.
- `.env`가 Git 제외 대상이고 `.env.example`의 키가 비어 있는 것을 확인했다.

근거: `docs/evidence/gemini_verification.json`, `gemini_http_flow.json`, `gemini_public_http_flow.json`. 모델·공개 입력·합성 이력의 검증 한계는 앞선 파트와 같다.

## 남은 항목

실제 생성형 RAG 호출 검증은 완료했다. 실제 브라우저 클릭·시연 영상, Pi·물리 음악, 실제 반려견 행동 정확도·장기 기록·케어 효과는 아직 미검증이다. 전체 목표를 완료로 처리하지 않는다.
