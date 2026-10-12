# PetMind — 개발 진행 기록 및 계획

AI 기반 반려견 행동 분석 및 IoT 스마트 급식 통합 시스템

---

## 📝 project3 변경 요약 (피드백1·2 반영)

project2.md를 기반으로 교수 피드백(`피드백1.md`, `피드백2.md`)을 반영해 개정한 문서다. 피드백은 음성 인식 결과를 정리한 것이라 일부 내용은 불확실하며, 아래 항목 중 "확인 필요"는 원본 녹음으로 재확인한다.

| 피드백 | 반영 내용 | 반영 위치 |
|---|---|---|
| 단일 이미지로는 "빙글빙글 돈다" 같은 **동작**을 판단할 수 없다. 영상 시퀀스와 LSTM 같은 시계열 모델이 필요하다 | 프레임별 행동 라벨을 시퀀스로 모아 동작을 분류하는 시계열 단계 추가 | 「피드백 반영 개선 계획」 1 |
| 영상·소리를 각각 텍스트로 만들어 LLM 컨텍스트에 넣는 구조가 맞는지 확인 | 현재 `PetContext` 구조가 이 방식과 일치함을 명시하고, 동작 결과를 입력 항목으로 추가 | 〃 2 |
| 짖음 감지가 "감지"라고만 적혀 있어 구체적이지 않다. 전처리·특징 추출·횟수 산출이 필요하다 | 짖음 감지 파이프라인 단계와 산출 지표를 구체화 | 〃 3 |
| 사용 모델이 목적에 맞는지, 감정 인식의 근거가 무엇인지 설명할 수 있어야 한다. AI 표정 모듈은 목적·차별성이 약하다 | 모델별 역할·한계·선택 근거 표 작성, 감정은 보조 신호로 유지 | 〃 4 |
| 심심해하는 반려견에게 LLM이 놀이·음악을 제안하고 음악을 틀어준다 (확인 필요) | 기존 "사전 등록 음악 + 보호자 승인" 정책을 유지하되 LLM이 음악 종류를 추천하는 확장으로 정리 | 〃 5 |
| 교수 취업·회사 관련 대화 (확인 필요) | 프로젝트 문서 범위가 아니므로 반영하지 않음 | — |
| (자체 검토) Raspberry Pi 5 구현 가능성 | CPU 추론 속도 목표 조정, pigpio 교체, 전원·발열, 실행 분담 반영 | 「Raspberry Pi 5 적합성 검토」 |

---

## 2026년 11월 7일 통합 시연 기준 (현재 기준 문서)

프로젝트의 핵심은 모델 간 정확도 경쟁이 아니라 **관찰 신호를 종합하고, 보호자 승인 후 안전하게 케어를 실행하는 전체 흐름**이다.

`카메라·마이크·센서 → 30초 상태 집계 → 케어 제안 → 보호자 승인 → 음악/급식 → 장치 완료 확인`

### 확정 개발 기간

- 시작일: **2026년 9월 28일**
- 최종 완료일: **2026년 11월 7일**
- 개발 기간: **6주**
- 완료 기준: 정상 휴식·불안 의심·급식 필요 시나리오를 재시작 없이 연속 실행하고, 제안 생성부터 승인 및 장치 결과 표시까지 시연

| 주차 | 기간 | 목표 및 완료 기준 |
|---|---|---|
| 1주차 | 9월 28일~10월 4일 | 기반 구조 확정, `PetContext`·DB·시뮬레이터 정리 및 백엔드 테스트 통과 |
| 2주차 | 10월 5일~10월 11일 | 규칙 기반 제공자, JSON 검증, 제안 생성·조회 API 안정화 |
| 3주차 | 10월 12일~10월 18일 | 승인·거절, 급식 안전 정책, MQTT 명령과 장치 완료 응답 검증 |
| 4주차 | 10월 19일~10월 25일 | Flutter 통합 화면, 환경별 API 주소, 시뮬레이터 전체 흐름 완성 |
| 5주차 | 10월 26일~11월 1일 | Raspberry Pi·카메라·센서·서보·로드셀 실장비 통합 및 오차 측정 |
| 6주차 | 11월 2일~11월 7일 | 장애 폴백 테스트, 연속 시연 리허설, 결과 지표와 복구 절차 확정 |

**내부 동결일은 11월 5일**로 두며, 이후에는 신규 기능을 추가하지 않고 치명적 오류 수정과 발표 리허설만 진행한다.

### 구현된 통합 기능

- `PetContext`: 행동 신뢰도·지속시간, 짖음, 온습도, 사료 잔량, 최근 급식 이력을 단일 입력으로 사용
- `LLMProvider`: 공급자 중립 인터페이스와 API 키 없이 동작하는 규칙 기반 기본 제공자
- `CareSuggestion`: 요약, 판단 근거, 주의 수준, 음악/급식 권장과 승인 가능 액션을 구조화
- FastAPI: `/care/evaluate`, `/care/latest`, `/care/history`, 승인·거절·장치 응답 API
- SQLite: 센서, 케어 제안, 실행 액션, 실제 급식량 및 실패 사유 기록
- 안전 정책: 1회 100g, 24시간 300g, 재급식 120분(환경변수로 조정)
- 장치 상태: `requested → acknowledged → completed/failed`, 무응답 명령 자동 시간 초과
- Flutter: 관찰 상태, 센서, 판단 근거, 승인/거절, 실행 이력 중심의 발표 화면
- 시뮬레이터: 정상 휴식, 불안 의심, 급식 필요 시나리오를 재현

### 범위 결정

- EfficientNet 감정 결과는 실험적 보조 신호로만 유지한다.
- 현재 YOLO 라벨은 확정 감정이 아니라 `시각 분류 신호`로 표시한다.
- 짖음은 감정 분류 없이 감지 여부·빈도·음량만 사용한다.
- 외부 LLM 공급자 결정 전에는 규칙 기반 제공자가 기본이며, 오류 시에도 같은 제공자로 폴백한다.
- 직접 급식 API는 기본 차단한다. 음악과 급식은 반드시 제안 생성과 보호자 승인을 거친다.
- 음악은 `petmind/assets/audio`의 사전 등록 파일만 재생한다.

### 피드백 반영 개선 계획

#### 1. 동작 인식: 단일 프레임 → 시계열

- **문제**: 현재 YOLOv8 행동 클래스(happy/anxious/playing/resting/alert)는 프레임 한 장 기준이다. "제자리에서 빙글빙글 돈다", "앉았다 일어났다 반복한다"처럼 시간에 따라 드러나는 동작은 판단할 수 없다.
- **방안**: 프레임별 YOLO 결과(행동 라벨·신뢰도·바운딩박스 중심 좌표 및 크기)를 일정 길이(예: 최근 N초)의 시퀀스로 모아 경량 LSTM(또는 GRU)으로 동작을 분류한다.
- **출력 예**: `spinning`(제자리 회전), `pacing`(왕복 이동), `sit_stand_repeat`(앉았다 일어남 반복), `still`(정지)
- **연결**: 분류 결과와 지속시간을 `PetContext`에 텍스트화 가능한 필드로 추가한다.
- **단계**:
  - [ ] 시퀀스 입력 설계 (프레임 간격, 윈도우 길이, 특징 벡터)
  - [ ] 학습 데이터 확보: 영상 데이터셋 조사 또는 직접 촬영·라벨링
  - [ ] 시뮬레이터에 동작 시퀀스 시나리오 추가
  - [ ] 데이터 확보가 어려우면 바운딩박스 이동량 기반 규칙(이동 거리·방향 전환 횟수)으로 대체 후, 시계열 모델은 확장 과제로 명시
- **정확도 원칙**: 5주차 실장비 통합에 영향을 주지 않도록 규칙 기반 폴백을 먼저 구현하고, LSTM은 그 위에 얹는다.

#### 2. LLM 입력 구조 (확인된 현행 구조)

영상·소리를 각각 텍스트(상태 요약)로 변환해 LLM 제공자에 전달하고, LLM이 상태를 해석해 케어 제안을 만드는 구조이며 현재 `PetContext` → `LLMProvider` → `CareSuggestion` 흐름과 일치한다.

| 입력 | 현재 | 추가 |
|---|---|---|
| 시각 표정/자세 | YOLO 행동 라벨·신뢰도·지속시간 | — |
| 시각 동작 | 없음 | 시계열 동작 분류 결과 (위 1) |
| 소리 | 짖음 여부·빈도·음량 | 윈도우별 횟수·구간 요약 (아래 3) |
| 환경·장치 | 온습도, 사료 잔량, 급식 이력 | — |

- LLM은 판단과 문장 생성만 담당하고, 급식·음악 실행은 계속 보호자 승인 이후 장치 명령으로만 수행한다.

#### 3. 짖음 감지 파이프라인 구체화

| 단계 | 내용 |
|---|---|
| 1. 수집 | 마이크 입력을 wav 프레임(예: 16kHz, 1초 윈도우)으로 연속 수집 |
| 2. 전처리 | 모노 변환, 정규화, 노이즈 임계값 보정 |
| 3. 특징 추출 | RMS 음량, 에너지 변화, 필요 시 MFCC·스펙트로그램 |
| 4. 감지 | 임계값/에너지 기반 감지로 시작, 데이터 확보 시 소형 분류기로 확장 |
| 5. 집계 | 30초 상태 집계 윈도우 안의 짖음 횟수, 평균 음량, 지속 구간 산출 |
| 6. 전달 | "30초 동안 N회 짖음" 형태의 요약을 `PetContext`에 입력 |

- 감정 분류는 하지 않는다 (기존 범위 결정 유지).
- 산출 지표: 윈도우당 짖음 횟수, 최대/평균 음량, 일간 누적 횟수.
- [ ] 짖음 샘플 녹음 또는 공개 데이터로 임계값 검증, 오탐/미탐 측정

#### 4. 모델 선택 근거와 한계

| 모델/모듈 | 역할 | 한계 | 시연에서의 위치 |
|---|---|---|---|
| YOLOv8n | 반려견 탐지, 자세·행동 분류 (mAP50 96.45%) | 프레임 단위라 동작 불가 | 핵심 시각 신호 |
| 시계열 모델(예정) | 동작 분류 | 데이터 필요 | 규칙 폴백과 병행 |
| EfficientNet-B0 | 감정 분류 | 얼굴 크롭으로 학습, 전신 이미지에서 정확도 낮음 | 실험적 보조 신호만 사용 |
| 짖음 감지 | 빈도·음량 | 감정 판별 불가 | 상태 집계 신호 |
| LLM 제공자 | 신호 종합 해석과 설명 생성 | 직접 관찰 불가, 입력 텍스트에 의존 | 규칙 기반이 기본, 외부 LLM은 선택 |

- 감정 인식의 근거를 발표에서 질문받을 수 있으므로, "정확한 감정 판정이 아니라 보조 신호"임을 명확히 설명한다.
- **차별점**: 개별 모델 정확도 경쟁이 아니라 표정·동작·소리·환경을 종합한 뒤 보호자 승인을 거쳐 안전하게 케어를 실행하는 흐름이다.

#### 5. 심심함 → 놀이·음악 제안 확장 (선택)

- 활동이 오래 없거나 지루해 보이는 상태에서 LLM이 놀이 방법과 어울리는 음악 종류를 제안한다.
- 음악 재생은 기존 정책(사전 등록된 `petmind/assets/audio` 파일, 보호자 승인)을 유지한다. 유튜브 실시간 검색·재생은 승인 없는 외부 콘텐츠 재생이 되므로 시연 범위에서 제외하고 확장 과제로 남긴다.
- 음악 재생 후 반려견 상태 변화(행동·짖음 변화)를 기록해 효과를 보여 주는 지표는 여유가 있을 때 추가한다.
- [ ] 제안 템플릿에 `play_suggestion` 필드와 음악 카테고리 추가

#### 일정 반영

| 주차 | 추가 작업 |
|---|---|
| 1~2주차 | 동작 입력 설계, 짖음 파이프라인 정의, `PetContext` 확장 필드 설계 |
| 3~4주차 | 규칙 기반 동작 분류와 짖음 집계 구현, 시뮬레이터 시나리오 반영, 모델 근거 표 정리 |
| 5주차 | **먼저 Pi 5 GPIO 호환 점검(pigpio 교체, DHT22 검증)과 추론 속도 실측**, 이어서 실장비 영상·마이크로 동작·짖음 임계값 검증 (시계열 모델은 데이터가 확보된 경우에 한해 적용) |
| 6주차 | 발표용 모델 한계·선택 근거 설명 자료 확정 |

### 로컬 시연 실행

```powershell
cd petmind/backend
python -m pip install -r ../requirements-dev.txt
$env:PETMIND_SIMULATE_ACTIONS="true"
uvicorn main:app --host 0.0.0.0 --port 8000
```

별도 터미널에서 시나리오를 넣고 Flutter 웹을 실행한다.

```powershell
cd petmind
python simulator.py all

cd ../petmind_app
flutter run -d chrome --dart-define=PETMIND_API_BASE=http://localhost:8000
```

실제 MQTT 왕복 검증 시에는 백엔드의 `PETMIND_SIMULATE_ACTIONS=false`, Raspberry Pi의 `PETMIND_DEVICE_SIMULATE=false`로 설정하고 `python -m hardware.device_agent`를 실행한다. 음원 파일은 `petmind/assets/audio/README.md`의 허용된 이름으로 준비한다.

> 기존 `petmind.db`에는 새 열과 테이블이 자동 마이그레이션되지 않는다. 개발 데이터라면 삭제 후 서버를 재시작하고, 보존할 데이터가 있다면 백업 후 마이그레이션해야 한다.

---

## 전체 개발 단계 요약

| 단계 | 내용 | 상태 |
|------|------|------|
| STEP 1 | 데이터 수집 및 환경 구성 | ✅ 완료 |
| STEP 2 | AI 모델 학습 (행동 + 감정) | ✅ 완료 |
| STEP 3 | Raspberry Pi 하드웨어 연동 | ⏳ 대기 (라파 부재) |
| STEP 4 | FastAPI 백엔드 서버 | ✅ 완료 |
| STEP 5 | 사용자 인터페이스 (대시보드 + 앱) | 🔄 진행 중 |

---

## ✅ STEP 1 — 데이터 수집 및 환경 구성 (완료)

### 데이터셋
- **행동 데이터**: Roboflow `dog-pose-annotation/dog-pose-feaal v12`
  - 클래스 재매핑: chien assis → resting(3), chien debout → alert(4), chien a pieds → playing(2)
- **감정 데이터**: Roboflow `dog-emotion-zaveh/dog-emotion-ovhny v2`
  - LABEL_MAP: happy → happy, relaxed → neutral, sad → sad, angry → angry

### 개발 환경
- OS: Windows 11 Home
- Python: 3.14.4
- GPU: AMD RX 7800 XT (Windows에서 CUDA 미지원 → Kaggle GPU 사용)
- 학습 플랫폼: Kaggle (T4 x2, 무료 티어 30hr/week)

---

## ✅ STEP 2 — AI 모델 학습 (완료)

### 2-1. YOLOv8 행동 인식 모델

| 항목 | 내용 |
|------|------|
| 모델 | YOLOv8n |
| 학습 플랫폼 | Kaggle Notebook (T4 x2) |
| 학습 파일 | `petmind/ai/behavior/train_kaggle.ipynb` |
| 에포크 | 100 (EarlyStopping 적용) |
| 배치 | 32, imgsz=640 |
| 최종 성능 | mAP50 **96.45%** |
| 가중치 위치 | `petmind/ai/behavior/weights/behavior_v1/weights/best.pt` (6.25 MB) |

**클래스 (5개):**
- 0: happy, 1: anxious, 2: playing, 3: resting, 4: alert

**트러블슈팅:**
- `fl_gamma` 파라미터 → Kaggle ultralytics 버전 미지원, 제거
- Kaggle Secrets 연결 → Notebook access 토글 활성화 필요
- GPU 없음 오류 → 전화번호 인증 후 T4 활성화
- best.pt가 .zip으로 다운로드 → `.pt.zip` → `.pt`로 이름 변경 (압축 해제 X)

---

### 2-2. EfficientNet-B0 감정 분류 모델

| 항목 | 내용 |
|------|------|
| 모델 | EfficientNet-B0 (torchvision) |
| 학습 플랫폼 | Kaggle Notebook (T4 x2) |
| 학습 파일 | `petmind/ai/emotion/train_kaggle.ipynb` |
| 에포크 | 50 |
| 배치 | 64, AdamW, CosineAnnealingLR |
| 가중치 위치 | `petmind/ai/emotion/weights/best.pt` (16.34 MB) |

**클래스 (4개):**
- happy, sad, angry, neutral

**현황:** 전신 이미지에서 감정 분류 정확도 낮음 (얼굴 크롭 이미지로 학습됨) → 추후 개선 예정

---

### 2-3. 통합 추론 파이프라인

- 파일: `petmind/ai/pipeline.py`
- 동작: YOLOv8로 반려견 탐지 → 바운딩박스 크롭 → EfficientNet으로 감정 분류
- 반환 형식:
  ```python
  [{"behavior": str, "behavior_conf": float, "emotion": str, "emotion_conf": float, "bbox": list}]
  ```
- 테스트: `dog.jpg`로 동작 확인 완료

**짖음 분류(bark):** 데이터셋 미확보 → 감정 분류 없이 에너지 기반 감지·빈도 집계로 구현 (「피드백 반영 개선 계획」 3 참조)

---

## ✅ STEP 4 — FastAPI 백엔드 서버 (완료)

### 구성

| 파일 | 역할 |
|------|------|
| `petmind/backend/main.py` | FastAPI 앱, CORS, 라우터 등록 |
| `petmind/backend/database.py` | SQLAlchemy ORM, SQLite DB |
| `petmind/backend/schemas.py` | Pydantic v2 스키마 |
| `petmind/backend/mqtt_client.py` | MQTT 발행 (paho-mqtt) |
| `petmind/backend/routers/analysis.py` | POST/GET /analysis/ |
| `petmind/backend/routers/feeding.py` | POST/GET /feeding/ |

### API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/` | 서버 상태 확인 |
| GET | `/health` | 헬스체크 |
| POST | `/analysis/` | 분석 결과 저장 |
| GET | `/analysis/` | 분석 기록 조회 (limit=50) |
| GET | `/analysis/latest` | 최신 분석 결과 |
| POST | `/feeding/` | 급식 명령 + 로그 저장 |
| GET | `/feeding/` | 급식 기록 조회 (limit=50) |

### MQTT 토픽
- `petmind/feeding/command` — 급식량(g) 전송 (라파 수신)
- `petmind/status` — 분석 결과 브로드캐스트

### 실행 방법
```powershell
cd petmind/backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Mosquitto 브로커
- winget으로 설치, Windows 서비스로 자동 실행 (`localhost:1883`)
- PC 재시작 후 자동으로 켜짐

---

## 🔄 STEP 5 — 사용자 인터페이스 (진행 중)

### 5-1. PyQt6 데스크톱 대시보드 ✅ 완료

- 파일: `petmind/dashboard/main.py`
- PyQt6 6.11.0

**기능:**
- 행동 인식 / 감정 분석 / 오늘 급식 횟수 카드
- 급식량(10~200g) 설정 + 수동 급식 실행 버튼
- 분석 기록 테이블 (최근 20건, 행동별 컬러)
- 급식 기록 테이블 (최근 20건)
- 백엔드 연결 상태 표시 (녹색/빨간색)
- 5초 주기 자동 갱신 (QThread로 비동기 처리, UI 프리징 없음)

**실행:**
```powershell
python petmind/dashboard/main.py
```

---

### 5-2. Flutter 웹/모바일 앱 🔄 진행 중

- 프로젝트: `petmind_app/`
- Flutter 3.32.4, Dart 3.8.1

**현재 상태:**
- 프로젝트 생성 완료 (`flutter create petmind_app --platforms web`)
- `http: ^1.2.2` 패키지 추가
- `lib/main.dart` 구현 완료

**기능 (구현 완료):**
- 행동 인식 / 감정 분석 / 오늘 급식 횟수 카드
- 급식량(+/- 10g) 조절 + 급식 실행 버튼 (로딩 인디케이터)
- 분석 기록 / 급식 기록 테이블
- 백엔드 연결 상태 표시
- 5초 주기 자동 갱신

**웹 실행:**
```powershell
cd petmind_app
flutter run -d chrome
```

**남은 작업:**
- [ ] 모바일(Android) 빌드 테스트
- [ ] 실시간 카메라 스트리밍 뷰 추가 (라파 연동 후)
- [ ] 푸시 알림 연동 (이상 행동 감지 시)

---

## ⏳ STEP 3 — Raspberry Pi 하드웨어 연동 (대기 중)

**라파 부재 중 (방학) → 복귀 후 진행**

### 예정 작업

| 항목 | 내용 |
|------|------|
| OS | Raspberry Pi OS 64-bit |
| 카메라 | picamera2로 프레임 캡처 → pipeline.py로 추론 |
| 급식 제어 | MQTT `petmind/feeding/command` 수신 → 서보모터 제어 |
| 로드셀 | HX711으로 사료 잔량 측정 → 백엔드 전송 |
| 온습도 | DHT22 → 팬 자동 제어 |
| 추론 최적화 | ONNX(또는 NCNN) 변환 + 입력 해상도 축소(320~416) + 필요 시 INT8 양자화. 목표는 **3~5FPS 이상**(30초 집계 방식이라 충분), 15FPS는 여유가 있을 때의 stretch 목표 |

### Raspberry Pi 5 적합성 검토

Pi 5(CPU 추론)로 구현 가능하다고 판단하며, 아래 조건을 따른다. 속도 수치는 일반적인 범위 기준이므로 5주차에 실측해 확정한다.

| 항목 | 판단 | 대응 |
|---|---|---|
| YOLOv8n | PyTorch 그대로는 640 해상도에서 약 3~5FPS 수준 | ONNX/NCNN 변환, 해상도 축소. 목표를 3~5FPS로 설정 |
| EfficientNet-B0 | 크롭 이미지 기준 가능, 매 프레임 실행은 불필요 | 1초에 1회, 탐지된 크롭에만 실행 |
| 시계열 모델·짖음 감지 | 부하 매우 낮음 | 그대로 Pi에서 실행 |
| **pigpio** | **Pi 5(RP1 칩) 미지원** | `gpiozero` + `lgpio` 또는 하드웨어 PWM 오버레이로 교체 |
| DHT22 | 일부 라이브러리가 Pi 5에서 타이밍 오류 | 읽기 성공 여부를 먼저 검증, 실패 시 libgpiod 기반 라이브러리 또는 I2C 센서(BME280 등)로 교체 |
| HX711(로드셀) | GPIO 라이브러리 의존 | pigpio 의존 여부 확인 후 `lgpio`/`gpiozero` 기반으로 점검 |
| picamera2 | Pi 5 지원 | Raspberry Pi OS 64-bit(Bookworm) 사용 |
| 전원·발열 | 서보 구동 시 전압 강하로 Pi 재부팅 위험, 연속 추론 시 발열 | 서보 별도 전원, 액티브 쿨러, 전원 어댑터 5V/5A급 |
| RAM | 4GB 가능, 8GB 권장 | — |

**실행 분담(권장)**
- **Raspberry Pi 5**: 카메라 추론, 마이크 처리, 센서·서보·팬 제어, MQTT 장치 에이전트(`device_agent`)
- **PC(또는 서버)**: FastAPI, SQLite, LLM 제공자, Flutter 앱 접속
- Pi와 서버는 MQTT·HTTP로 연결해 Pi 부하를 줄이고 시연 안정성을 높인다.

**대안(선택)**: 속도가 부족하면 Raspberry Pi AI Kit(Hailo-8L) 추가를 검토한다. 모델을 HEF 포맷으로 변환해야 하고 비용이 들어 필수 항목은 아니다.

### 하드웨어 파일 (이미 작성됨)
- `petmind/hardware/camera.py`
- `petmind/hardware/servo.py` ← pigpio 사용 시 Pi 5용으로 교체 필요
- `petmind/hardware/loadcell.py` ← GPIO 라이브러리 점검
- `petmind/hardware/dht22.py` ← Pi 5 동작 검증 필요
- `petmind/hardware/fan.py` ← GPIO 라이브러리 점검

---

## 앞으로 남은 작업 (우선순위 순)

### 단기 (라파 없이 가능)
- [ ] 동작 인식 시계열 단계 설계 및 규칙 기반 폴백 구현 (피드백 반영)
- [ ] 짖음 감지 파이프라인 구체화 및 `PetContext` 연동 (피드백 반영)
- [ ] 모델별 선택 근거·한계 정리 (피드백 반영)
- [ ] Flutter 앱 Android 빌드 테스트
- [ ] 감정 모델 개선 (전신 이미지 대응, 파인튜닝)
- [ ] 백엔드 이상 행동 감지 → 알림 로직 구현
- [ ] Flutter 앱 알림 수신 기능 추가

### 라파 복귀 후
- [ ] **Pi 5 GPIO 호환 점검**: pigpio를 쓰는 서보·로드셀·팬 코드를 `gpiozero`/`lgpio` 기반으로 교체, DHT22 읽기 검증 (가장 먼저 진행)
- [ ] Pi에 pipeline.py 이식 및 추론 속도 실측 (YOLO·EfficientNet 각각 FPS와 지연시간, CPU 온도)
- [ ] MQTT 연동 (급식 명령 수신 + 상태 발행)
- [ ] 서보모터 급식량 캘리브레이션 (목표: ±5g)
- [ ] 로드셀 사료 잔량 백엔드 연동
- [ ] ONNX/NCNN 변환 + 해상도 축소 + 필요 시 INT8 양자화 (목표 3~5FPS 이상)
- [ ] 서보 별도 전원 구성, 쿨러 장착 후 장시간(30분 이상) 연속 구동 안정성 확인
- [ ] 전체 시스템 통합 테스트 (AI → 백엔드 → 하드웨어 → 앱)
- [ ] 실제 반려견 환경 필드 테스트

### 최종 목표 (2026년 11월 7일 캡스톤 발표)
- [ ] 실시간 동작 시연 가능한 완성형 시제품
- [ ] mAP50 96%+ 행동 인식 유지
- [ ] 감정 분류 정확도 85% 이상 달성
- [ ] 급식량 오차 ±5g 이내
- [ ] 원격 제어 응답 시간 1초 이내

---

## 현재 로컬 파일 구조

```
(찐)졸업작품/
├── petmind/
│   ├── ai/
│   │   ├── behavior/
│   │   │   ├── train.py                  # 로컬 학습 스크립트
│   │   │   ├── train_kaggle.ipynb        # Kaggle 학습 노트북 ✅
│   │   │   ├── inference.py
│   │   │   └── weights/behavior_v1/weights/best.pt  # 6.25MB (gitignore)
│   │   ├── emotion/
│   │   │   ├── train_kaggle.ipynb        # Kaggle 학습 노트북 ✅
│   │   │   ├── model.py                  # EfficientNet-B0 정의
│   │   │   ├── inference.py
│   │   │   └── weights/best.pt           # 16.34MB (gitignore)
│   │   ├── bark/                         # 짖음 분류 (보류)
│   │   └── pipeline.py                  # 통합 추론 파이프라인 ✅
│   ├── backend/
│   │   ├── main.py                       # FastAPI 앱 ✅
│   │   ├── database.py                   # SQLAlchemy + SQLite ✅
│   │   ├── schemas.py                    # Pydantic v2 ✅
│   │   ├── mqtt_client.py                # paho-mqtt ✅
│   │   └── routers/
│   │       ├── analysis.py               # ✅
│   │       └── feeding.py                # ✅
│   ├── hardware/                         # Raspberry Pi 제어 코드
│   └── dashboard/
│       └── main.py                       # PyQt6 대시보드 ✅
├── petmind_app/                          # Flutter 웹/모바일 앱 🔄
│   └── lib/main.dart
├── project2.md                           # 이전 버전
└── project3.md                           # 이 파일 (피드백 반영본)
```

---

## 주요 기술 스택

| 구분 | 기술 |
|------|------|
| AI (행동) | YOLOv8n (Ultralytics 8.4.x) |
| AI (감정) | EfficientNet-B0 (torchvision) |
| 학습 플랫폼 | Kaggle (T4 x2 GPU) |
| 데이터 | Roboflow API |
| 백엔드 | FastAPI + SQLAlchemy + SQLite |
| 통신 | MQTT (paho-mqtt, Mosquitto 브로커) |
| 데스크톱 UI | PyQt6 6.11.0 |
| 모바일/웹 | Flutter 3.32.4 |
| 하드웨어 | Raspberry Pi 5, picamera2, gpiozero + lgpio (pigpio는 Pi 5 미지원이라 교체) |
