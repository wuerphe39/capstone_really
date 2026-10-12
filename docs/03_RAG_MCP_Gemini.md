# 파트 3 — 개별 기록 검색·MCP·Gemini

검증일: 2026-10-11

## 완료한 연결

- `services/retrieval.py`: 반려견·최근 7일·현재 관찰 이전 시각으로 필터링한 SQLite 기록 검색. 라벨·요약 키워드 관련도와 최신순으로 최대 5건을 고른다. 최대 최근 1,000건을 집계하며 제한을 응답에 표시한다.
- `mcp_server.py`: 공식 MCP Python SDK 2.3.0의 stdio 서버. `search_observations`, `get_observation_stats`, `get_care_history` 읽기 전용 도구.
- `mcp_client.py`: 백엔드가 별도 서버 프로세스를 실행해 도구 3개를 실제 호출한다. SDK의 텍스트 JSON/구조화 결과 형식을 처리한다.
- `providers.py`: 기존 규칙·Gemini 인터페이스를 현재 관찰과 검색 근거를 받도록 확장. 집계 정보만 전송한다. 규칙 결과와 Gemini 결과를 구분한다.
- `services/care.py`: 검색 근거·통계·도구 호출 결과와 인용 ID를 DB에 함께 저장. 검색 실패와 성공했지만 기록이 없는 상태를 구분한다.
- Gemini가 없는 기록을 인용하거나 호출/검증에 실패하면 `rule-fallback`으로 표시한다.

## 검증 증거

- 전체 **29 passed** 중 MCP 테스트는 mock이 아닌 실제 Python subprocess·stdio 왕복이다.
- 실제 HTTP 3개 시나리오에서 MCP 성공 제안 3건. 각 제안의 근거에 도구 3개의 성공 상태와 같은 반려견 기록이 남았다.
- 다른 반려견·미래 관찰·현재 관찰은 과거 근거에 섞이지 않는다.
- 허위 인용 ID는 규칙 폴백으로 전환되는 테스트 통과.

## 최신 실제 호출 검증

파트 14에서 환경 파일 설정과 출력 스키마를 수정했다. 실제 Gemini RAG·MCP·인용 검증, 합성 3종의 Gemini HTTP 응답 3건, 공개 입력의 실제 제안·가상 실행을 확인했다. 아래 내용은 키 설정 전의 기록이다.

## 키 설정 전의 미완료 기록

Gemini API 키가 없어 실제 Gemini 응답 성공은 **0건**이다. 사용자가 로컬 `.env` 설정 후 알리기로 했으며, 키를 확인한 뒤 실제 호출·근거 인용·오류 폴백을 추가 검증한다. 현재 규칙 제공자 결과를 생성형 RAG 검증 성공으로 발표하지 않는다.

검색은 벡터 검색 대신 SQLite·키워드·기간 필터 방식이다. 한국어 문장 검색과 자연어 질문 품질은 아직 평가 전이다. MCP 서버는 현재 평가 요청마다 실행하며, 동시 사용자 성능 개선은 전체 흐름 검증 이후 수행한다.

참고: [공식 MCP SDK](https://github.com/modelcontextprotocol/python-sdk), [Gemini 구조화 출력](https://ai.google.dev/gemini-api/docs/structured-output).
