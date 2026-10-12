// Artifact capture from stored real API outputs, not a browser integration test.
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:petmind_app/main.dart';

void main() {
  testWidgets('capture saved public-input dashboard', (tester) async {
    final data = jsonDecode(File('../artifacts/ui_snapshot.json').readAsStringSync()) as Map<String, dynamic>;
    final media = data['media'] as Map<String, dynamic>;
    final pet = data['pet_id'].toString();
    final preview = FileImage(File('../artifacts/video/preview.jpg'));
    await tester.runAsync(() async {
      final loader = FontLoader('SnapshotFont');
      final bytes = await File('C:/Windows/Fonts/malgun.ttf').readAsBytes();
      loader.addFont(Future.value(ByteData.sublistView(bytes)));
      await loader.load();
      final icons = FontLoader('MaterialIcons');
      final iconBytes = await File('C:/Users/kuro/develop/flutter/bin/cache/artifacts/material_fonts/MaterialIcons-Regular.otf').readAsBytes();
      icons.addFont(Future.value(ByteData.sublistView(iconBytes)));
      await icons.load();
    });
    tester.view.physicalSize = const Size(1200, 3400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final client = MockClient((request) async {
      final path = request.url.path;
      final dynamic result = request.method == 'POST' && path == '/media/observe' ? media
        : path == '/care/evaluate' || path == '/care/latest' ? data['suggestion']
        : path == '/observations' ? [media['observation']]
        : path == '/care/actions/recent' ? data['actions']
        : path == '/timeline' ? data['timeline']
        : path == '/metrics' ? data['metrics']
        : path == '/media/catalog' ? {
          ...data['catalog'], 'files': [
            for (final file in data['catalog']['files'])
              if (file['filename'] == media['sources'][0]['filename']) file,
            for (final file in data['catalog']['files'])
              if (file['filename'] != media['sources'][0]['filename']) file,
          ],
        }
        : path.endsWith('/profile') ? data['profile'] : [];
      return http.Response(jsonEncode(result), 200, headers: {'content-type': 'application/json; charset=utf-8'});
    });
    await tester.pumpWidget(MaterialApp(theme: ThemeData(brightness: Brightness.dark,
      fontFamily: 'SnapshotFont', colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xff6750a4), brightness: Brightness.dark)),
      home: RepaintBoundary(key: const ValueKey('capture'), child: DashboardPage(
        client: client, initialPetId: pet, previewProvider: preview))));
    await tester.pumpAndSettle();
    await tester.runAsync(() => precacheImage(preview, tester.element(find.byType(DashboardPage))));
    await tester.tap(find.text('공개 입력 분석·케어 제안'));
    await tester.pumpAndSettle();
    await expectLater(find.byKey(const ValueKey('capture')), matchesGoldenFile('../../artifacts/flutter_dashboard.png'));
    await tester.pumpWidget(const SizedBox());
  });
}
