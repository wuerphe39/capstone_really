# 발표자료 안내

중간발표(2026-10-13)와 그 이후에 쓰거나 만든 자료를 한곳에 정리한 문서다. **발표 당시 자료**는 그때의 사실을 기록한 것이므로 이후 결정(Raspberry Pi 미사용, YAMNet 채택)과 다를 수 있다. 최신 구조는 맨 아래 "현재 기준"을 따른다.

## 1. 발표 PPT

| 파일 | 상태 | 비고 |
|---|---|---|
| [PetMind_3주차발표자료.pptx](../docs/presentation/PetMind_3주차발표자료.pptx) | **발표에 사용한 원본** (23장) | Raspberry Pi 사용, 음성 LSTM 운영으로 서술. 발표 후 결정이라 수정하지 않기로 함 |
| [PetMind_3주차발표자료_최신화.pptx](../docs/presentation/PetMind_3주차발표자료_최신화.pptx) | 참고용 복사본 | 슬라이드 4, 9, 11, 21, 22에 "YAMNet 기준 전환" 문구를 넣은 것. 발표 자료는 고치지 않기로 해서 사용하지 않음 |
| [PetMind_설명.docx](../docs/presentation/PetMind_설명.docx) | 슬라이드별 설명 원고 | 발표 당시 기준 |

## 2. 동영상

| 파일 | 상태 | 비고 |
|---|---|---|
| [영상/중간발표 동작 영상.mp4](영상/중간발표%20동작%20영상.mp4) | 화면 녹화 원본 (41초) | 터미널에서 YAMNet 데모를 공개 음원 4개로 실행. 오른쪽에 Claude 채팅창이 보임 |
| [영상/중간발표 동작 영상_자막.mp4](영상/중간발표%20동작%20영상_자막.mp4) | **자막 입힌 최종본** | 장면별 설명 자막. 마이크·웹캠·Pi는 미검증이라는 문구는 마지막 자막에서 뺌 |
| [영상/중간발표 동작 영상_자막.srt](영상/중간발표%20동작%20영상_자막.srt) | 자막 파일 | 영상에 이미 입혀져 있음. 다른 플레이어용 |

영상 파일은 용량과 개인 정보 때문에 Git에 올리지 않는다(`.git/info/exclude`).

이 PC의 `artifacts/demo_video/`에는 로그를 터미널 모양으로 다시 그린 `petmind_yamnet_terminal_demo.mp4`(와 `.srt`)와 점수 그래프 영상 `petmind_yamnet_demo.mp4`가 있다. 두 영상은 같은 음원의 점수가 다르게 나오므로(전체 구간 계산 대 1.5초 창 계산) **발표에는 함께 쓰지 않는다.**

**웹 서비스 시연 영상**(docs/39, 40이 설명하는 약 3분 영상)은 이 PC에 없고 기존 작업 PC의 `artifacts/presentation_20261011/`에 있다.

## 3. 블록도

| 파일 | 상태 | 비고 |
|---|---|---|
| [PetMind_동작_애니메이션.html](../PetMind_동작_애니메이션.html) / [.svg](../PetMind_동작_애니메이션.svg) | **최신** | 교수님 스케치 반영: 마이크·웹캠 PC 직결, YAMNet 로컬, DB → MCP → 클라우드 LLM → API. 8단계. README 맨 위에 삽입됨. 생성기는 `scripts/build_flow_animation.py` |
| [docs/PetMind_실장비_블록도.html](../docs/PetMind_실장비_블록도.html), [docs/presentation/PetMind_블록도.html](../docs/presentation/PetMind_블록도.html), [docs/PetMind_전체_블록도.svg](../docs/PetMind_전체_블록도.svg) | 발표 당시 | Raspberry Pi 포함 구조. 현재와 다름 |
| [참고/교수님 블록도 피드백.jpg](참고/교수님%20블록도%20피드백.jpg) | 교수님 화이트보드 스케치 | 마이크 → 라파 → Windows(YAMNet local → 짖음 감지 → DB), MCP, Cloud(Google Gemini), API. 공개 저장소에는 올리지 않음 |

## 4. 대본

| 파일 | 상태 | 비고 |
|---|---|---|
| [대본/중간발표_대본.docx](대본/중간발표_대본.docx) | 발표 전 작성 | 음성 모델 비교, 동작 영상 멘트, 예상 질문. 발표 시점 기준 |

## 5. 제출 문서 (이 폴더 밖: [../제출문서/](../제출문서/))

졸업작품 계획서(별지3호)와 지도계획서(별지4호)를 수정한 docx와 학과 서식 원본이 있다. 팀원 연락처가 들어 있어 Git에 올리지 않는다. 폰트는 서식 PDF와 같은 휴먼명조다.

## 현재 기준 (발표 이후 결정)

- Raspberry Pi 5는 사용하지 않는다. 마이크와 웹캠은 PC(노트북)에 직접 연결한다.
- 음성 감지는 YAMNet을 쓴다(PC에서 로컬 실행).
- 클라우드 LLM(Gemini)은 외부 서비스로 분리해서 표현한다.
- 위 변경은 README의 "범위 변경(2026-10-13)" 안내와 블록도 애니메이션에 반영돼 있다. **README 4장, AGENTS.md, 코드의 일부 문구는 아직 LSTM 기준이다.**
