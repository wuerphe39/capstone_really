import 'package:flutter/material.dart';
import 'clip_view.dart';

class CameraPanel extends StatefulWidget {
  const CameraPanel({super.key, required this.base});
  final String base;
  @override
  State<CameraPanel> createState() => _CameraPanelState();
}

class _CameraPanelState extends State<CameraPanel> {
  bool opened = false;
  @override
  Widget build(BuildContext context) => Card(
    child: Padding(padding: const EdgeInsets.all(20), child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('최근 카메라 장면', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 8),
        const Text('라즈베리파이 웹캠이 수집한 최근 장면을 확인하세요. 자동 외출 중에는 약 5초 구간이 닫힌 뒤 갱신되므로 지연됩니다.\n'
          '장비 연결 후 사용할 수 있습니다. 카메라 보기는 녹화나 음성 분석을 시작하지 않습니다.'),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          icon: Icon(opened ? Icons.videocam_off_outlined : Icons.videocam_outlined),
          label: Text(opened ? '카메라 화면 닫기' : '카메라 화면 열기'),
          onPressed: () => setState(() => opened = !opened),
        ),
        if (opened) SizedBox(height: 460, child: clipView('${widget.base}/camera/view')),
        const SizedBox(height: 8),
        const Text('음성 감지로 저장된 사건 영상은 아래 외출 기록의 원본 근거에서 확인합니다.'),
      ],
    )),
  );
}
