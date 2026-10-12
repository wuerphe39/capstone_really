import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:petmind_app/camera_panel.dart';

void main() {
  testWidgets('camera opens only on request and closes', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: Scaffold(
      body: SingleChildScrollView(child: CameraPanel(base: 'http://localhost:8010')))));
    expect(find.text('최근 카메라 장면'), findsOneWidget);
    expect(find.text('카메라 화면 닫기'), findsNothing);
    await tester.tap(find.text('카메라 화면 열기'));
    await tester.pump();
    expect(find.text('카메라 화면 닫기'), findsOneWidget);
    await tester.tap(find.text('카메라 화면 닫기'));
    await tester.pump();
    expect(find.text('카메라 화면 열기'), findsOneWidget);
  });
}
