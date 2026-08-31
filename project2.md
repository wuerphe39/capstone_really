# PetMind — 개발 진행 기록 및 계획

AI 기반 반려견 행동 분석 및 IoT 스마트 급식 통합 시스템

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

**짖음 분류(bark):** 데이터셋 미확보 → 선택적 추가 기능으로 보류

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
| 추론 최적화 | ONNX 변환 + INT8 양자화로 15FPS 목표 |

### 하드웨어 파일 (이미 작성됨)
- `petmind/hardware/camera.py`
- `petmind/hardware/servo.py`
- `petmind/hardware/loadcell.py`
- `petmind/hardware/dht22.py`
- `petmind/hardware/fan.py`

---

## 앞으로 남은 작업 (우선순위 순)

### 단기 (라파 없이 가능)
- [ ] Flutter 앱 Android 빌드 테스트
- [ ] 감정 모델 개선 (전신 이미지 대응, 파인튜닝)
- [ ] 백엔드 이상 행동 감지 → 알림 로직 구현
- [ ] Flutter 앱 알림 수신 기능 추가

### 라파 복귀 후
- [ ] Pi에 pipeline.py 이식 및 실시간 추론 테스트
- [ ] MQTT 연동 (급식 명령 수신 + 상태 발행)
- [ ] 서보모터 급식량 캘리브레이션 (목표: ±5g)
- [ ] 로드셀 사료 잔량 백엔드 연동
- [ ] ONNX 변환 + 양자화로 추론 속도 최적화
- [ ] 전체 시스템 통합 테스트 (AI → 백엔드 → 하드웨어 → 앱)
- [ ] 실제 반려견 환경 필드 테스트

### 최종 목표 (11월 캡스톤 발표)
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
└── project2.md                           # 이 파일
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
| 하드웨어 | Raspberry Pi 5, picamera2, pigpio |
