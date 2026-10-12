# PetMind Raspberry Pi 테스트 폴더

이 폴더는 가상 음악 장치의 PC↔Pi 명령 왕복 검증용이다. 스피커·GPIO·카메라·마이크를 실제로 제어하지 않는다.

위치: `/home/pi/Desktop/PetMind_Test`. Python 3.13.5 / Debian 13.5 / ARM64. `.venv`에 requests 2.34.2를 설치했다.

## 연결·실행

PC에서 백엔드를 127.0.0.1:8010으로 실행한 다음 아래 SSH 터널을 유지한다.

```powershell
ssh -N -R 127.0.0.1:18010:127.0.0.1:8010 -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=3 raspberrypi-ai
```

Pi의 127.0.0.1:18010은 터널이 유지되는 동안 PC API로 연결된다. 별도 터미널에서:

```powershell
ssh raspberrypi-ai /home/pi/Desktop/PetMind_Test/.venv/bin/python /home/pi/Desktop/PetMind_Test/pi_probe.py
ssh raspberrypi-ai sh /home/pi/Desktop/PetMind_Test/run_once.sh
```

Pi에서 직접 실행:

```bash
cd /home/pi/Desktop/PetMind_Test
sh run_once.sh
# 상시 에이전트
.venv/bin/python device_agent.py --base http://127.0.0.1:18010 --cache commands.db
```

명령 하나만 시험하려면 `sh run_once.sh --command-id 명령ID`를 사용한다. 실패 응답 시험은 `--outcome failed`를 추가한다. 무응답 시간초과 시험 중에는 PC와 Pi의 상시 에이전트를 종료한다.

## 결과

`pi_verification.json`과 `TEST_RESULT.md`에 실제 검증 결과를 저장한다. `commands.db`는 명령 ID별 결과 캐시다. 터널 종료 뒤에는 PC API 연결이 종료되며, 터널을 다시 열어 재시험한다.
