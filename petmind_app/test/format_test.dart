import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:petmind_app/format.dart';
import 'package:petmind_app/main.dart' show resolveApiBase;

void main() {
  test('UTC ISO becomes Korean time without seconds', () {
    expect(formatKst('2026-10-22T14:10:28.641331Z'), '2026-10-22 23:10');
  });

  test('date rolls over after UTC 15:00', () {
    expect(formatKst('2026-10-22T16:05:00Z'), '2026-10-23 01:05');
  });

  test('empty, null and non-time values do not break the screen', () {
    expect(formatKst(null), '');
    expect(formatKst(''), '');
    expect(formatKst('not a time'), 'not a time');
  });

  test('known sources get Korean names and unknown ones stay as is', () {
    expect(sourceLabel('user_audio'), '사용자 음원');
    expect(sourceLabel('live'), '실시간 수집');
    expect(sourceLabel('something_new'), 'something_new');
    expect(sourceLabel(null), '');
  });

  testWidgets('a broken widget shows its reason instead of a gray box', (tester) async {
    final old = ErrorWidget.builder;
    ErrorWidget.builder = readableErrorBox;
    try {
      await tester.pumpWidget(Directionality(textDirection: TextDirection.ltr,
        child: Builder(builder: (context) => throw StateError('bad field'))));
      expect(tester.takeException(), isNotNull);
      expect(find.textContaining('bad field'), findsOneWidget);
    } finally {
      ErrorWidget.builder = old;  // flutter_test checks this before tearDown callbacks run
    }
  });

  group('resolveApiBase', () {
    test('an explicit address is used as given', () {
      expect(resolveApiBase('http://localhost:8010', Uri.parse('http://192.168.0.5:8010/')), 'http://localhost:8010');
    });
    test('auto follows the page address and uses the API port', () {
      expect(resolveApiBase('auto', Uri.parse('http://localhost:8021/')), 'http://localhost:8010');
      expect(resolveApiBase('auto', Uri.parse('http://192.168.0.5:8010/#/home')), 'http://192.168.0.5:8010');
      expect(resolveApiBase('auto', Uri.parse('http://192.168.0.5:8021/')), 'http://192.168.0.5:8010');
    });
  });
}
