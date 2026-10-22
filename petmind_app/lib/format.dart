/// 화면에 보이는 시각과 출처 이름을 사람이 읽기 쉬운 형태로 바꾼다.
library;

import 'package:flutter/widgets.dart';

/// UTC ISO 문자열(예: 2026-10-22T14:10:28.641331Z)을 한국 시간 `2026-10-22 23:10`으로 바꾼다.
/// 시각이 아니거나 비어 있으면 원래 값을 그대로 돌려준다(화면이 깨지지 않게).
String formatKst(Object? iso) {
  final text = '${iso ?? ''}';
  if (text.isEmpty) return '';
  final parsed = DateTime.tryParse(text);
  if (parsed == null) return text;
  final utc = parsed.isUtc ? parsed : DateTime.utc(parsed.year, parsed.month, parsed.day, parsed.hour, parsed.minute, parsed.second);
  final kst = utc.add(const Duration(hours: 9));
  String two(int v) => v.toString().padLeft(2, '0');
  return '${kst.year}-${two(kst.month)}-${two(kst.day)} ${two(kst.hour)}:${two(kst.minute)}';
}

const _sourceLabels = {
  'user_audio': '사용자 음원',
  'live': '실시간 수집',
  'synthetic_demo': '합성 시연',
  'public_media': '공개 자료',
  'guardian_input': '보호자 입력',
};

/// 내부 출처 값을 한국어 이름으로 바꾼다. 모르는 값은 그대로 보여 준다.
String sourceLabel(Object? source) {
  final key = '${source ?? ''}';
  return _sourceLabels[key] ?? key;
}

/// 화면 일부를 그리다 예외가 나면 Flutter 릴리스 빌드는 이유 없이 큰 회색 상자만 보여 준다.
/// 대신 원인을 한 줄로 알려 주는 작은 상자를 그려, 한 항목의 문제가 화면 전체를 가리지 않게 한다.
Widget readableErrorBox(FlutterErrorDetails details) {
  final message = '${details.exception}'.split('\n').first;
  return Container(
    padding: const EdgeInsets.all(8),
    decoration: BoxDecoration(
      color: const Color(0xFFFFF7E6),
      border: Border.all(color: const Color(0xFFE0B050)),
      borderRadius: BorderRadius.circular(6),
    ),
    child: Text('이 항목을 표시하지 못했습니다. ($message)',
      textDirection: TextDirection.ltr,
      style: const TextStyle(fontSize: 12, color: Color(0xFF6B4A00))),
  );
}
