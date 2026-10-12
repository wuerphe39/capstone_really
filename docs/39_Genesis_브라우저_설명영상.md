# Genesis UI와 공개 음원 시연 설명 영상

기준일: 2026-10-11. 로컬 영상: `artifacts/presentation_20261011/petmind_genesis_browser_walkthrough.mp4`. **실제 로컬 브라우저 화면 캡처를 편집한 설명 영상이며, 연속 클릭 화면 녹화는 아니다.** 약 2분 57초, 1920×1080 H.264/AAC다. 영상 원본과 합성 음성은 Git에서 제외한 `artifacts/`에 남긴다. GitHub에서 영상 파일을 직접 열 수는 없으며, 같은 PC에서 경로를 열거나 아래 명령으로 재생성한다.

| 구간 | 내용 | 화면·수치의 근거 |
|---|---|---|
| 00:00–00:18 | 기존 다크 UI와 Genesis 적용 UI 비교 | [화면 비교](37_Genesis_UI_적용_비교.md) |
| 00:18–00:36 | 실제 브라우저 첫 화면·외출 흐름 | `verified_browser_dashboard_top.png` |
| 00:36–01:02 | 공개 Dog 음원 감지, 원본 5초 재생, 업로드 후 입력 초기화 | `verified_browser_second_upload_reset.png`, ESC-50 `5-203128-A-0.wav` |
| 01:02–01:25 | 동일 모델이 놓친 공개 Dog 사례 | `verified_browser_audio_review.png`, ESC-50 `1-100032-A-0.wav` |
| 01:25–01:47 | 앞의 놓친 사례 한 건이 연결된 외출의 귀가 요약·시연 출처·관찰 근거 | `verified_browser_summary.png` |
| 01:47–02:09 | 시간 질문에 표본·판단 불가·출처 근거로 답하는 화면 | `verified_browser_duration_question.png` |
| 02:09–02:33 | 기존 LSTM과 증강·MIL 후보의 동일 평가 자료 F1 | [`audio_lstm_three_way.json`](evidence/audio_lstm_three_way.json) |
| 02:33–02:57 | 실제 가정 음향·사람 정답·독립 평가의 남은 과제 | 현재 구현·검증 한계 |

ESC-50 음원은 공식 평가 분할의 공개 자료이며, 영상에는 실제 보호자 기록이나 반려견 감정·질환 판정이 없다. `5-203128-A-0.wav`의 원본 해시를 확인해 삽입했다. 화면의 `93.9/100`과 `44.5/100`은 특정 5초 입력의 실험 점수이고 정확도·확률이 아니다. FSD50K 평가 F1은 기존 0.436, 증강 후보 0.430으로 낮아 운영 체크포인트를 유지했다. 후보의 검증 점수 상승을 실제 현장 정확도 향상으로 소개하지 않는다.

시연용 네 파일은 공식 ESC-50의 ESC-10 부분집합으로 데이터셋 라이선스는 **CC BY 3.0**이다. 각 원본은 공식 `LICENSE`에 **CC0**로 기재되어 있다. 준비 명령은 공식 라이선스 파일에서 아래 원저작자·원본 페이지를 추출해 `demo_manifest.json`에 기록한다. 검증한 분할·출처·원본 ID·SHA-256은 [발표 음원 manifest](evidence/esc50_presentation_audio_manifest.json)에도 남겼다. 영상에 직접 삽입한 것은 첫 번째 Dog 음원 한 개이며 원저작자 표기를 영상 화면에도 넣었다.

| ESC-50 음원 | 원본 제공자·링크 | 공식 분할 |
|---|---|---:|
| `5-203128-A-0.wav` | [Pierre Grandjean · Freesound #203128](https://www.freesound.org/people/Pierre%20Grandjean/sounds/203128/) | 5 |
| `5-208030-A-0.wav` | [Mewsel · Freesound #208030](https://www.freesound.org/people/Mewsel/sounds/208030/) | 5 |
| `5-181766-A-10.wav` | [laura222 · Freesound #181766](https://www.freesound.org/people/laura222/sounds/181766/) | 5 |
| `1-100032-A-0.wav` | [nfrae · Freesound #100032](https://www.freesound.org/people/nfrae/sounds/100032/) | 1 |

재생성은 저장소 루트에서 아래 명령을 실행한다. 네 공개 음원은 별도 준비 명령이 공식 메타데이터·파일 해시로 검증해 Git 제외 `artifacts/datasets/esc50_demo/`에 둔다. 감지 사례와 놓친 사례 모두 [ESC-50 공식 자료](https://github.com/karolpiczak/ESC-50)의 평가 분할에 속하며 새 독립 평가로 계산하지 않는다. 생성 스크립트는 현재 저장된 브라우저 스크린샷, Windows 한국어 음성 합성, 공개 음원, 고정 평가 JSON을 사용한다.

```powershell
python -m scripts.prepare_demo_audio
python -m scripts.build_genesis_browser_walkthrough
```

실행 후 비디오의 시작·55초·112초·165초 프레임이 디코딩되는 것을 확인했다. AAC에서 55~60초의 개 소리 구간을 디코딩해 원본과 비교한 상관계수는 약 0.9997이었다. 합성 내레이션 파일 8개와 공개 음원은 재생성 결과에 포함된다. 영상은 발표의 준비된 설명 자료로 쓴다.

**별도 연속 브라우저 조작 영상:** `artifacts/presentation_20261011/petmind_full_continuous_browser_demo.mp4`는 새 시연 DB에서 Edge 브라우저를 자동 조작하며 녹화한 **30.6초 무음 화면**이다. 사용자 음원 외출 시작 → 공식 ESC-50 Dog WAV 선택 → 공개 자료 출처·저장 동의 → 업로드·분석 → 시연 담당자 의견 저장 → 외출 종료 → 근거 요약 → 관찰 #1 원본 플레이어 열기가 한 번의 화면 녹화에 이어진다. 편집 영상과 달리 화면 전환을 이어 붙이지 않았다. 실제 사용자가 손으로 클릭한 녹화나 현장 음성은 아니며, 단일 공개 음원 흐름을 보여줄 뿐 감지 정확도를 입증하지 않는다. H.264 1280×720 전체 765프레임을 오류 없이 디코딩하고 시작·중간·원본 대화상자 프레임을 직접 확인했다. 별도 DB에는 종료된 외출 1건, 음원/관찰 1건, 시연 담당자 의견, 분석 표본 5초가 남았다. 영상과 DB는 Git 제외 `artifacts/`에만 둔다.

## 현장 브라우저 시연 순서

먼저 저장소 루트에서 `python -m scripts.prepare_demo_audio`로 네 음원을 준비한다. 기존 README대로 Python·Flutter 의존성을 설치한 뒤, **별도 터미널**에서 백엔드와 화면을 실행한다. 아래 DB 경로는 발표 시연 전용이며 개인 기록과 섞지 않는다. 현재 체크포인트는 Git에 없으므로 다른 PC로 옮길 때 `artifacts/audio_lstm/esc50_lstm.pt`를 별도로 준비하거나 모델 미준비 표시를 그대로 설명한다. 규칙 제공자는 Gemini 키 없이도 근거 설명 흐름을 시연할 수 있으며, 생성형 응답이라고 소개하지 않는다.

```powershell
# 터미널 1 — 저장소 루트, 활성화한 Python 환경에서
New-Item -ItemType Directory -Force artifacts/presentation_20261011 | Out-Null
$env:PETMIND_DATABASE_URL = 'sqlite:///artifacts/presentation_20261011/live_demo.db'
$env:PETMIND_LLM_PROVIDER = 'rule'
$env:PETMIND_RETRIEVAL_MODE = 'local'
python -m uvicorn petmind.backend.main:app --host 127.0.0.1 --port 8010

# 터미널 2 — 저장소 루트에서
cd petmind_app
flutter run -d chrome --web-port 8021 --dart-define=PETMIND_API_BASE=http://127.0.0.1:8010
```

브라우저를 열기 전에 `http://127.0.0.1:8010/health`에서 `status: healthy`와 `audio_lstm_checkpoint_present`를 확인한다. `false`면 점수 비교를 시연할 수 없으므로 원본·확인 의견·근거 흐름만 보여준다. 시연 기록에 노출되는 반려견은 실제 개인 정보가 아닌 `demo-dog` 같은 시연용 ID를 쓴다.

첫 화면을 새로고침한 직후에는 한글 대체 글꼴과 API 기록이 아직 로딩 중일 수 있다. 제목이 정상 한글로 표시되고 상단 상태가 **연결됨**으로 바뀐 뒤 시연을 시작한다.

1. **사용자 음원** 입력 모드로 외출을 시작한다. `artifacts/datasets/esc50_demo/audio/5-203128-A-0.wav`를 선택하고 **공개 자료 시연용 음원**을 체크한다. 출처에 `ESC-50 / 5-203128-A-0.wav`를 적고 시연용 저장 동의를 체크한 뒤 업로드한다. 실제 LSTM 점수는 준비한 체크포인트와 입력 환경에 따라 확인한다.
2. **음원 듣기**와 **구간 듣기**로 원본 5초를 확인한다. 분석 창 5초는 짖음의 정확한 시작·끝이 아니다. **확인 의견**에는 ‘시연 담당자 의견’이 붙으며 모델 정답으로 쓰지 않는다.
3. `1-100032-A-0.wav`를 같은 방식으로 업로드한다. 개발 PC에서 이 Dog 파일은 기준값을 넘지 못해 놓친 사례였다. 새 환경의 결과가 다르면 화면의 실제 점수를 설명하고 이전 점수 44.5/100을 재현된 결과라고 주장하지 않는다. 추가 Dog `5-208030-A-0.wav`도 저장된 기본 LSTM 평가에서 점수 0.040으로 기준 0.9에 못 미쳤다([평가 기록](evidence/audio_baselines_esc50.json)). rain 파일 `5-181766-A-10.wav`는 일반 소리 대조용이다. 이 네 파일만으로 전체 성능을 계산하지 않는다.
4. **귀가·외출 종료 → 근거 기반 요약 → 원본 근거**를 보여준다. 위 순서로 서로 다른 5초 음원 두 개를 같은 외출에 올리면 분석 표본은 10초다. 영상 속 5초 요약은 놓친 사례 한 건만 연결된 이전 화면이므로 현장 수치와 같다고 소개하지 않는다. 두 경우 모두 외출 전체 녹음 시간이 아니다. 이어 **하루 근거 설명**에서 “얼마나 오래 봤는지 알려줘”를 물어 표본 시간과 영상 판단 불가를 확인한다. 규칙 제공자 화면에는 실제 사용 제공자가 표시된다.
5. 종료 전에 시연 전용 DB만 보존하고 공개 음원 출처·모델 미준비 여부·놓침 사례를 발표 기록에 적는다. 기존 개인 DB나 학습 체크포인트는 Git에 올리지 않는다.

첫 번째 외출을 `demo-dog`로 종료한 뒤 두 번째 비교용 외출을 준비하려면, **같은 시연 API를 켜 둔 상태**에서 저장소 루트의 별도 터미널에서 `python -m scripts.prepare_presentation_demo`를 실행할 수 있다. 이 명령은 두 번째 Dog·rain 음원을 공개 시연 자료로 업로드하고 의견·질문 결과를 `artifacts/presentation_20261011/demo_api.json`에 남긴다. 결과의 `model_results`에는 실행 당시 파일별 점수·기준값·기준 통과 여부를 따로 적는다. 모델이 없으면 ‘놓침’이라고 단정하는 메모를 쓰지 않는다. 다른 포트나 ID를 쓰면 `--base`·`--pet-id` 옵션을 지정한다. 이미 두 외출이 있다면 새 기록을 만들지 않고 기존 기록을 검증한다.
