# 파트 18 — 기존 VS Code SSH 설정 확인

검증일: 2026-10-11

사용자 요청에 따라 기본 SSH 설정과 VS Code의 Remote SSH 설정을 확인했다. 개인 키 내용이나 비밀번호는 읽거나 출력하지 않았다.

기본 `~/.ssh/config`에 `rp` 별칭, HostName `192.168.0.10`, User `pi`, Port `22`가 있다. VS Code 설정에서 별도의 SSH configFile 지정은 확인되지 않았다.

읽기 전용 연결 확인:

```powershell
ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=yes rp uname -a
```

결과는 `Permission denied (publickey,password)`였다. SSH 서버 응답까지 확인했지만 현재 비대화형 인증은 통과하지 못했다. 호스트 검증을 해제하거나 개인 키·비밀번호를 변경하지 않았다. Pi의 OS·Python·하드웨어 정보는 원격 명령이 실행되지 않아 아직 확인할 수 없다.

이후 기존 계정으로 사용할 SSH 키/에이전트 인증 또는 사용자 측의 정상 로그인 상태를 준비하면 `rp` 설정을 활용해 가상 장치 왕복 테스트를 진행할 수 있다. 비밀번호나 개인 키는 채팅에 전달하지 않는다.
