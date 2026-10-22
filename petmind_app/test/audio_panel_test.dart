import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:petmind_app/audio_panel.dart';

void main() {
  testWidgets('HTML server error shows a readable audio retry message', (tester) async {
    final client = MockClient((_) async => http.Response('<html>proxy error</html>', 503));
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: AudioPanel(
      client: client, base: 'http://localhost', petId: 'dog-a', onChanged: () {}))));
    await tester.pumpAndSettle();
    await tester.tap(find.text('사용자 음원 · 보호자 확인'));
    await tester.pumpAndSettle();
    expect(find.textContaining('HTTP 503').last, findsOneWidget);
    expect(find.textContaining('proxy error'), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('clip with missing review and window scores still renders', (tester) async {
    tester.view.physicalSize = const Size(1200, 1500);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final clip = {'id': 'clip-x', 'observation_id': 3, 'duration_s': 5, 'training_consent': false,
      'expires_at': '2026-10-18T00:00:00Z', 'deleted': false, 'audio_available': true,
      'source_note': '수집', 'analysis': {'audio_model': {'model_name': 'YAMNet Bark', 'windows': [{'label': 'other'}]}}};
    final client = MockClient((request) async => request.url.path.endsWith('/review-queue')
      ? http.Response(jsonEncode({'items': []}), 200, headers: {'content-type': 'application/json; charset=utf-8'})
      : http.Response(jsonEncode([clip]), 200, headers: {'content-type': 'application/json; charset=utf-8'}));
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: SingleChildScrollView(child: AudioPanel(
      client: client, base: 'http://localhost', petId: 'dog-a', onChanged: () {})))));
    await tester.pumpAndSettle();
    await tester.tap(find.text('사용자 음원 · 보호자 확인'));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(find.textContaining('관찰 #3'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('older clips load page by page and a refresh keeps them', (tester) async {
    tester.view.physicalSize = const Size(1200, 1500);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    Map<String, dynamic> clip(int n) => {'id': 'clip-$n', 'observation_id': n, 'duration_s': 5,
      'training_consent': false, 'expires_at': '2026-10-18T00:00:00Z', 'deleted': false,
      'audio_available': false, 'review_priority': 'routine_sample', 'source_note': '수집', 'analysis': {}, 'review': {}};
    final all = [for (var n = 130; n >= 1; n--) clip(n)];  // newest first, like the server
    final requested = <String>[];
    final client = MockClient((request) async {
      if (request.url.path.endsWith('/review-queue')) {
        return http.Response(jsonEncode({'items': []}), 200, headers: {'content-type': 'application/json; charset=utf-8'});
      }
      requested.add(request.url.query);
      final limit = int.parse(request.url.queryParameters['limit'] ?? '100');
      final offset = int.parse(request.url.queryParameters['offset'] ?? '0');
      final page = all.skip(offset).take(limit).toList();
      return http.Response(jsonEncode(page), 200, headers: {'content-type': 'application/json; charset=utf-8'});
    });
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: SingleChildScrollView(child: AudioPanel(
      client: client, base: 'http://localhost', petId: 'dog-a', onChanged: () {})))));
    await tester.pumpAndSettle();
    await tester.tap(find.text('사용자 음원 · 보호자 확인'));
    await tester.pumpAndSettle();
    expect(find.textContaining('관찰 #130 '), findsOneWidget);
    expect(find.textContaining('관찰 #30 '), findsNothing);          // beyond the first 100
    final more = find.textContaining('이전 음원 더 보기');
    await tester.ensureVisible(more);
    await tester.tap(more);
    await tester.pumpAndSettle();
    expect(find.textContaining('관찰 #30 '), findsOneWidget);
    expect(find.textContaining('관찰 #1 '), findsOneWidget);          // the oldest clip is reachable
    expect(find.textContaining('이전 음원 더 보기'), findsNothing);     // a short page was the last one
    expect(requested.any((q) => q.contains('offset=100')), isTrue);
    await tester.ensureVisible(find.text('음원 목록 새로고침'));
    await tester.tap(find.text('음원 목록 새로고침'));                    // refresh asks for everything shown
    await tester.pumpAndSettle();
    expect(requested.last.contains('limit=130'), isTrue);
    expect(find.textContaining('관찰 #1 '), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('review queue failure still shows clips and recovers', (tester) async {
    tester.view.physicalSize = const Size(1200, 1500);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    var queueOnline = false;
    final clip = {'id': 'clip-1', 'observation_id': 9, 'duration_s': 5,
      'training_consent': false, 'expires_at': '2026-10-18T00:00:00Z',
      'deleted': false, 'audio_available': true, 'review_priority': 'uncertain',
      'source_note': '공개 시연 음원', 'analysis': {}, 'review': {}};
    final client = MockClient((request) async {
      if (request.url.path.endsWith('/review-queue')) {
        if (!queueOnline) return http.Response('{"detail":"unavailable"}', 503);
        return http.Response(jsonEncode({'items': [clip]}), 200,
          headers: {'content-type': 'application/json; charset=utf-8'});
      }
      return http.Response(jsonEncode([clip]), 200,
        headers: {'content-type': 'application/json; charset=utf-8'});
    });
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: SingleChildScrollView(
      child: AudioPanel(client: client, base: 'http://localhost', petId: 'dog-a',
        onChanged: () {})))));
    await tester.pumpAndSettle();
    await tester.tap(find.text('사용자 음원 · 보호자 확인'));
    await tester.pumpAndSettle();
    expect(find.text('관찰 #9 · 5초'), findsOneWidget);
    expect(find.textContaining('전체 음원 목록은 표시 중'), findsOneWidget);
    queueOnline = true;
    await tester.tap(find.text('음원 목록 새로고침'));
    await tester.pumpAndSettle();
    expect(find.text('확인 추천 1건 보기'), findsOneWidget);
    expect(find.textContaining('전체 음원 목록은 표시 중'), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('each upload requires a fresh source and consent', (tester) async {
    tester.view.physicalSize = const Size(1200, 1800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    var uploads = 0;
    String? uploadedSource;
    final client = MockClient((request) async {
      if (request.method == 'POST' && request.url.path == '/audio-clips/upload') {
        uploads++;
        uploadedSource = request.url.queryParameters['demo_source'];
        expect(request.url.queryParameters['store_consent'], 'true');
        expect(request.url.queryParameters['training_consent'], 'false');
        return http.Response('{}', 201);
      }
      final dynamic result = request.url.path.endsWith('/review-queue')
        ? {'items': []} : [];
      return http.Response(jsonEncode(result), 200);
    });
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: SingleChildScrollView(
      child: AudioPanel(client: client, base: 'http://localhost', petId: 'dog-a',
        onChanged: () {}, inputBuilder: (onSelected, onError) => TextButton(
          onPressed: () => onSelected('demo.wav', Uint8List.fromList([1, 2, 3])),
          child: const Text('선택 WAV')))))));
    await tester.pumpAndSettle();
    await tester.tap(find.text('사용자 음원 · 보호자 확인'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('선택 WAV'));
    await tester.tap(find.text('공개·생성 자료 시연용 음원'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'ESC-50 / old.wav');
    await tester.tap(find.text('공개·생성 자료 시연용 음원'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('공개·생성 자료 시연용 음원'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('시연용 기록으로 음원 저장에 동의'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('음원 업로드·분석'));
    await tester.pumpAndSettle();
    expect(uploads, 0);
    expect(find.textContaining('시연 음원 설명을 5자 이상'), findsOneWidget);
    await tester.enterText(find.byType(TextField), 'ESC-50 / new.wav');
    await tester.tap(find.text('음원 업로드·분석'));
    await tester.pumpAndSettle();
    expect(uploads, 1);
    expect(uploadedSource, 'ESC-50 / new.wav');
    expect(find.text('선택: demo.wav'), findsNothing);
    final boxes = tester.widgetList<CheckboxListTile>(find.byType(CheckboxListTile)).toList();
    expect(boxes[0].value, false);
    expect(boxes[1].value, false);
    final uploadButton = tester.widget<FilledButton>(find.ancestor(
      of: find.text('음원 업로드·분석'), matching: find.byType(FilledButton)));
    expect(uploadButton.onPressed, isNull);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('separate consent, guardian review and withdrawal', (tester) async {
    tester.view.physicalSize = const Size(1200,2400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    var consent = true;
    Map<String,dynamic> review = {};
    final client = MockClient((request) async {
      if (request.method == 'POST') {
        final body = jsonDecode(request.body);
        expect(body['pet_id'],'dog-a');
        if (request.url.path.endsWith('/review')) review = body;
        if (request.url.path.endsWith('/consent')) consent = body['training_consent'];
        return http.Response('{}',200);
      }
      return http.Response(jsonEncode([{'id':'clip','observation_id':4,'duration_s':5,
        'training_consent':consent,'expires_at':'2026-10-18','deleted':false,'audio_available':true,
        'review_priority':'uncertain','analysis':{'audio_lstm':{'dog_score':0.8,'threshold':0.5,
          'windows':[{'start_s':0,'end_s':5,'dog_score':0.8,'label':'dog_candidate'}]}},'review':review}]),200,
        headers:{'content-type':'application/json; charset=utf-8'});
    });
    await tester.pumpWidget(MaterialApp(home:Scaffold(body:SingleChildScrollView(child:AudioPanel(
      client:client,base:'http://localhost',petId:'dog-a',onChanged:() {})))));
    await tester.pumpAndSettle();
    await tester.tap(find.text('사용자 음원 · 보호자 확인'));
    await tester.pumpAndSettle();
    expect(find.textContaining('5초 창은 정확한 발성'),findsOneWidget);
    expect(find.textContaining('80.0 / 100 · 기준 50.0 / 100'),findsOneWidget);
    expect(find.text('구간 듣기'),findsOneWidget);
    final boxes = tester.widgetList<CheckboxListTile>(find.byType(CheckboxListTile)).toList();
    expect(boxes[0].value,false); expect(boxes[1].value,false);
    expect(boxes[2].value,false); expect(boxes[2].onChanged,isNull);
    await tester.tap(find.text('개인 관찰 기록으로 음원 저장에 동의'));
    await tester.pumpAndSettle();
    expect(tester.widgetList<CheckboxListTile>(find.byType(CheckboxListTile)).last.onChanged,isNotNull);
    await tester.tap(find.text('확인 의견'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField),'보호자가 확인한 상황');
    await tester.tap(find.text('의견 저장'));
    await tester.pumpAndSettle();
    expect(review['label'],'uncertain'); expect(review['note'],'보호자가 확인한 상황');
    expect(find.textContaining('보호자 의견: 판단하기 어려움'),findsOneWidget);
    await tester.tap(find.text('학습 참여 철회'));
    await tester.pumpAndSettle();
    expect(consent,false);
    expect(find.text('학습 참여 철회'),findsNothing);
    await tester.tap(find.text('공개·생성 자료 시연용 음원'));
    await tester.pumpAndSettle();
    expect(find.text('시연용 기록으로 음원 저장에 동의'), findsOneWidget);
  });
}
