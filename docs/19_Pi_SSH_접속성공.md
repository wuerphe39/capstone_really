# 파트 19 — 변경된 SSH 설정 접속 성공

검증일: 2026-10-11

SSH 별칭이 `rp`에서 `raspberrypi-ai`로 변경됐고 기존 Ed25519 인증 파일이 설정됐다. 개인 키 내용은 읽거나 출력하지 않았다. 이전 별칭은 더 이상 설정에 없으므로 새 별칭을 사용한다.

```powershell
ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=yes raspberrypi-ai uname -a
ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=yes raspberrypi-ai python3 --version
ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=yes raspberrypi-ai cat /etc/os-release
```

모든 원격 조회가 성공했다. 확인한 환경:

- SSH 별칭: raspberrypi-ai
- 주소/사용자/포트: 192.168.0.10 / pi / 22
- 호스트 이름: iot
- 아키텍처: aarch64 (ARM64)
- 커널: 6.18.34+rpt-rpi-2712
- OS: Debian GNU/Linux 13 (trixie), 13.5
- Python: 3.13.5

비대화형 SSH 인증이 정상 동작하므로 이 설정으로 추가 원격 검증을 진행할 수 있다. 이번 확인은 SSH 연결과 환경 조회이며 PetMind의 PC↔Pi 왕복, 물리 음악·카메라·마이크 테스트를 완료한 것은 아니다. 다음 단계에서는 가상 장치 에이전트의 의존성과 실행 환경을 확인하고 승인된 명령 수신·응답·이력 보존을 검증한다.
