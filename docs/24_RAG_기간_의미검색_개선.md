# 파트 24 — 기간 해석·의미 검색·피드백 근거 RAG

작성일: 2026-10-11. 기존 FastAPI·SQLite·공식 MCP·Gemini 구조를 유지했다. 별도 벡터 DB나 새 프레임워크를 도입하지 않았다.

## 수정 파일과 해결한 문제

| 파일 | 변경·이유 |
|---|---|
| `services/query_plan.py` | 오늘·어제·최근 N일/주/개월·시간대와 질문 의도 해석. 한국 시간 날짜를 UTC 경계로 변환 |
| `services/retrieval.py` | 반려견·기간 필터 후 키워드+임베딩 순위. 보호자 피드백·케어 제안/장치 결과 포함. 무관한 0점 최신 기록의 강제 반환 제거 |
| `services/embeddings.py` | 실제 `gemini-embedding-001`, 문서/질문 task 분리, 768차원 정규화, 모델·차원·task·내용 해시 기반 SQLite 캐시 |
| `mcp_server.py`, `mcp_client.py`, `services/care.py` | 동일한 정확한 기간 경계를 검색·통계·케어 조회에 전달, 검색 계획과 폴백 이유 저장 |
| `providers.py` | 배경 기록·의미 유사도·보호자 의견·음악 완료를 과대해석하지 않도록 지시 |
| `settings.py`, `.env.example` | `PETMIND_SEMANTIC_SEARCH=on` 지원. 로컬 `.env` 활성화 후 서버 재시작 |
| `tests/test_rag_quality.py`, `tests/test_flow.py` | 시간 경계·다른 반려견/미래 필터·피드백 검색·무관한 질문·임베딩 실패. 일반 테스트는 유료/외부 API 호출 제외 |
| `scripts/evaluate_rag.py`, `scripts/verify_rag_v2.py` | 검색 평가와 실제 embedding→MCP→Gemini→인용 통합 검증 |
| `petmind_app/lib/main.dart` | 검색 기간·의미 검색 여부·연결 실패·최신 배경 기록 구분 표시 |

기본 케어 질문에는 최근 배경 기록을 반환하되 `recent_context`로 구분한다. 특정 질문에 관련 없는 기록을 직접 근거로 취급하지 않도록 한다. 보호자 의견은 관찰 정답이 아니다. 역사 상태를 재구성할 시각이 없는 제안 상태는 `historical_status_unavailable`로 표시한다. 미래 feedback 및 늦게 갱신된 action 상태는 과거 질의에 포함하지 않는다.

의미 검색 실패 시 키워드 검색으로 이어가며 `lexical_fallback`과 오류 종류만 저장한다. API 키·오류 응답 전문은 기록하지 않는다. 원본 기록 DB는 조회용이고 별도 `artifacts/rag/embedding_cache.db`는 파생 검색 캐시다. pet/time 필터를 먼저 적용한다.

## 검색 품질 검증

초인종·천둥·택배·외출·음악 의견 등 **자체 작성한 20개 사건 메모/의역 질문**의 정답 ID를 고정해 비교했다. 실제 보호자 데이터나 독립 외부 벤치마크가 아니다.

| 방식 | Recall@5 | MRR |
|---|---:|---:|
| 이전 요약/라벨 키워드 방식 | 25% | 이번 보고서에서 별도 산출하지 않음 |
| 개선 키워드 + 보호자 메모 | 35% | 0.2542 |
| 개선 키워드 + 실제 Gemini 의미 검색 | 100% | 0.7475 |

의미 검색에서 Top-1은 12/20(60%)다. 따라서 100%는 첫 답이 모두 맞았다는 뜻이 아니다. 무관한 ‘화성 우주선 연료’ 질문은 근거 0건을 반환했다. 질문별 순위·응답 시간: [의미 검색 결과](evidence/rag_v2_semantic_evaluation.json), [키워드 결과](evidence/rag_v2_lexical_evaluation.json).

현재 의미 유사도 0.55 기준은 초기 설정이다. 최대 최근 1,000개 기록 중 의미 검색 대상은 최근 100개, 키워드 대상은 1,000개다. 장기 기록 전체를 검색하거나 실제 질문에서 오탐을 보장할 수준은 아니다. 기간·의도 해석도 제한된 규칙이며 모든 자연어 표현을 이해하지 않는다. ‘밤’은 해당 한국 날짜 18~24시로 정의한다.

## 실제 통합 검증

서버를 새 코드로 재시작했다. 고유 테스트 반려견에 합성 과거 관찰과 ‘초인종’ 보호자 의견을 저장한 뒤, ‘오늘 문 앞에서 벨 소리가 났을 때 반응’을 질문했다.

- 공식 MCP 도구 3개 호출 성공.
- 실제 `gemini-embedding-001` 검색 성공, 폴백 아님.
- 실제 `gemini-3.5-flash-lite` 응답, 폴백 아님.
- 과거 관찰 #54 검색·인용, 현재 #55 및 다른 반려견은 근거에 없음.
- LSTM 특징 v2 출처가 케어 문맥까지 전달됨.

응답·근거: [실제 통합 JSON](evidence/rag_v2_real_integration.json). 실제 API 검증은 합성 입력을 사용했으므로 실제 개 상태 판정 성능과 다르다. 전체 Python **52 passed**, Flutter **2 passed**, analyze·release web build 통과. 실제 브라우저 클릭 녹화는 이 검증에 포함하지 않았다.

새 모델로 공개 영상·음원→MCP→Gemini 흐름도 재실행했다. 이번 답변은 관찰 정보만 제안했고 음악 액션을 만들지 않았다. 실제 HTTP 출력으로 UI snapshot과 `artifacts/flutter_dashboard.png`를 다시 생성해 시각 확인했다. 이 PNG는 Flutter 테스트 렌더러의 출력이며 브라우저 캡처가 아니다. 백엔드 8010·웹 8020 HTTP 200을 확인했다.

```powershell
.\.venv\Scripts\python.exe -X utf8 -m scripts.evaluate_rag --semantic
.\.venv\Scripts\python.exe -X utf8 -m scripts.verify_rag_v2
```

## 다음 작업

실제 보호자 질문을 평가용으로 따로 확보해 무관한 기록 반환율·Recall@5·인용과 서술의 일치·지연을 평가한다. 질문 계획은 현재 의도 분류를 기록하지만 전문적인 의도별 추론 엔진은 아니다. 20개 자체 평가만으로 답변의 사실성·케어 효과·감정 판정이 검증됐다고 발표하지 않는다.

API 근거: [Gemini 임베딩 공식 문서](https://ai.google.dev/gemini-api/docs/embeddings).
