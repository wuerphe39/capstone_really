# PetMind Care 앱

2026년 11월 7일 통합 시연의 기본 UI다. 최신 관찰·센서 상태와 케어 제안 근거를 표시하고, 보호자가 음악 또는 급식을 승인하거나 거절할 수 있다.

```powershell
flutter pub get
flutter run -d chrome --dart-define=PETMIND_API_BASE=http://localhost:8000
```

Raspberry Pi와 같은 네트워크에서 실행할 때는 `localhost` 대신 백엔드 PC의 LAN 주소를 전달한다.

```powershell
flutter run -d chrome --dart-define=PETMIND_API_BASE=http://192.168.0.10:8000
```
