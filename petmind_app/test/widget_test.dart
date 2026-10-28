import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:petmind_app/main.dart';
import 'package:petmind_app/genesis_theme.dart';

void main() {
  testWidgets('sections isolate content and preserve question; leaving home closes camera', (tester) async {
    tester.view.physicalSize = const Size(1200, 1800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final client = MockClient((request) async {
      final path = request.url.path;
      final dynamic data = path == '/care/latest' || path.endsWith('/profile') ? null
        : path == '/metrics' || path == '/media/catalog' ? {}
        : path == '/outings/day' ? {'moments': [], 'sample_seconds': 0, 'unknown_seconds': 0}
        : path == '/audio-clips/review-queue' ? {'items': []} : [];
      return http.Response(jsonEncode(data), 200);
    });
    await tester.pumpWidget(MaterialApp(home: DashboardPage(client: client)));
    await tester.pumpAndSettle();
    expect(find.text('최근 관찰'), findsOneWidget);
    expect(find.text('외출 시작'), findsNothing);
    expect(find.text('휴식 시연'), findsNothing);
    await tester.tap(find.text('카메라 화면 열기'));
    await tester.pumpAndSettle();
    expect(find.text('카메라 화면 닫기'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('nav-2')));
    await tester.pumpAndSettle();
    expect(find.text('실시간 카메라'), findsNothing);
    await tester.enterText(find.byType(TextField), '지난번과 비교해 줘');
    await tester.tap(find.byKey(const ValueKey('nav-3')));
    await tester.pumpAndSettle();
    expect(find.text('전체 처리 타임라인'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('nav-2')));
    await tester.pumpAndSettle();
    expect(find.text('지난번과 비교해 줘'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('nav-0')));
    await tester.pumpAndSettle();
    expect(find.text('카메라 화면 열기'), findsOneWidget);
    expect(find.text('카메라 화면 닫기'), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('audio outing reports its actual mode when another input is chosen', (tester) async {
    tester.view.physicalSize = const Size(1200, 2600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    var sentScenario = false;
    final client = MockClient((request) async {
      final path = request.url.path;
      if (request.method == 'POST' && path == '/demo/observe') sentScenario = true;
      final dynamic result = path == '/outings'
        ? [{'id': 'audio-active', 'status': 'active', 'input_mode': 'uploaded_audio',
            'input_note': '사용자 음원', 'started_at': '2026-10-11T08:00:00Z'}]
        : path.endsWith('/summary') || path == '/outings/day'
        ? {'moments': [], 'sample_seconds': 0, 'unknown_seconds': 0,
            'bark_candidate_count': 0}
        : path == '/audio-clips/review-queue' ? {'items': []}
        : path == '/care/latest' || path.endsWith('/profile') ? null
        : path == '/metrics' || path == '/media/catalog' ? {} : [];
      return http.Response(jsonEncode(result), 200,
        headers: {'content-type': 'application/json; charset=utf-8'});
    });
    await tester.pumpWidget(MaterialApp(home: DashboardPage(client: client)));
    await tester.pumpAndSettle();
    final scenario = find.text('휴식 시연');
    await tester.tap(find.byKey(const ValueKey('nav-4')));
    await tester.pumpAndSettle();
    await tester.ensureVisible(scenario);
    await tester.tap(scenario);
    await tester.pumpAndSettle();
    expect(sentScenario, isFalse);
    expect(find.textContaining('진행 중 외출은 사용자 음원 모드입니다'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('server outage shows a retry path and recovers', (tester) async {
    var online = false;
    final client = MockClient((request) async {
      if (!online) return http.Response('{"detail":"offline"}', 503);
      final path = request.url.path;
      final dynamic result = path == '/care/latest' || path.endsWith('/profile')
        ? null : path == '/metrics' || path == '/media/catalog'
        ? {} : path == '/outings/day'
        ? {'moments': [], 'sample_seconds': 0, 'unknown_seconds': 0}
        : path == '/audio-clips/review-queue' ? {'items': []} : [];
      return http.Response(jsonEncode(result), 200);
    });
    await tester.pumpWidget(MaterialApp(home: DashboardPage(client: client)));
    await tester.pumpAndSettle();
    expect(find.text('연결 끊김'), findsOneWidget);
    expect(find.textContaining('백엔드 실행을 확인한 뒤 다시 연결'), findsOneWidget);
    expect(find.textContaining('503'), findsNothing);
    online = true;
    await tester.tap(find.text('다시 연결'));
    await tester.pumpAndSettle();
    expect(find.text('연결됨'), findsOneWidget);
    expect(find.textContaining('백엔드 실행을 확인한 뒤 다시 연결'), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('optional media failure keeps observations available and can recover', (tester) async {
    var failCatalog = true;
    var catalogRequests = 0;
    final client = MockClient((request) async {
      final path = request.url.path;
      if (path == '/media/catalog') catalogRequests++;
      if (path == '/media/catalog' && failCatalog) {
        return http.Response('{"detail":"catalog unavailable"}', 503);
      }
      final dynamic result = path == '/care/latest' || path.endsWith('/profile')
        ? null : path == '/observations'
        ? [{'id': 7, 'source': 'synthetic_demo', 'observed_at': '2026-10-11T00:00:00Z'}]
        : path == '/metrics' || path == '/media/catalog'
        ? {} : path == '/outings/day'
        ? {'moments': [], 'sample_seconds': 0, 'unknown_seconds': 0}
        : path == '/audio-clips/review-queue' ? {'items': []} : [];
      return http.Response(jsonEncode(result), 200);
    });
    await tester.pumpWidget(MaterialApp(theme: GenesisTheme.light,
      home: DashboardPage(client: client)));
    await tester.pumpAndSettle();
    expect(find.text('연결됨'), findsOneWidget);
    expect(find.textContaining('공개 자료 목록을 불러오지 못했습니다'), findsOneWidget);
    expect(catalogRequests, 1);
    await (tester.state(find.byType(DashboardPage)) as dynamic).refresh(silent: true);
    await tester.pumpAndSettle();
    expect(catalogRequests, 1);
    expect(find.textContaining('공개 자료 목록을 불러오지 못했습니다'), findsOneWidget);
    await tester.drag(find.byType(ListView).first, const Offset(0, -1000));
    await tester.pumpAndSettle();
    expect(find.textContaining('관찰 #7 · 합성 시연'), findsOneWidget);
    failCatalog = false;
    await tester.drag(find.byType(ListView).first, const Offset(0, 1000));
    await tester.pumpAndSettle();
    await tester.tap(find.text('다시 연결'));
    await tester.pumpAndSettle();
    expect(catalogRequests, 2);
    expect(find.textContaining('공개 자료 목록을 불러오지 못했습니다'), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('timeline and metrics failures keep observations available', (tester) async {
    var extrasOnline = false;
    final client = MockClient((request) async {
      final path = request.url.path;
      if (!extrasOnline && (path == '/timeline' || path == '/metrics')) {
        return http.Response('{"detail":"temporary"}', 503);
      }
      final dynamic result = path == '/care/latest' || path.endsWith('/profile')
        ? null : path == '/observations'
        ? [{'id': 8, 'source': 'user_audio', 'observed_at': '2026-10-11T00:00:00Z'}]
        : path == '/metrics' || path == '/media/catalog'
        ? {} : path == '/outings/day'
        ? {'moments': [], 'sample_seconds': 0, 'unknown_seconds': 0}
        : path == '/audio-clips/review-queue' ? {'items': []} : [];
      return http.Response(jsonEncode(result), 200);
    });
    await tester.pumpWidget(MaterialApp(home: DashboardPage(client: client)));
    await tester.pumpAndSettle();
    expect(find.text('연결됨'), findsOneWidget);
    expect(find.textContaining('핵심 관찰 기록은 표시 중입니다'), findsOneWidget);
    final state = tester.state(find.byType(DashboardPage)) as dynamic;
    expect(state.connectionIssue as String, contains('처리 타임라인'));
    expect(state.connectionIssue as String, contains('집계 지표'));
    await tester.drag(find.byType(ListView).first, const Offset(0, -1000));
    await tester.pumpAndSettle();
    expect(find.textContaining('관찰 #8 · 사용자 음원'), findsOneWidget);
    extrasOnline = true;
    await tester.drag(find.byType(ListView).first, const Offset(0, 1000));
    await tester.pumpAndSettle();
    await tester.tap(find.text('다시 연결'));
    await tester.pumpAndSettle();
    expect(find.textContaining('핵심 관찰 기록은 표시 중입니다'), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('older refresh cannot replace a newer observation', (tester) async {
    final firstObservation = Completer<http.Response>();
    var observationRequests = 0;
    final client = MockClient((request) async {
      final path = request.url.path;
      if (path == '/observations') {
        observationRequests++;
        if (observationRequests == 1) return firstObservation.future;
        return http.Response(jsonEncode([{'id': 2, 'source': 'new',
          'observed_at': '2026-10-11T00:00:00Z'}]), 200);
      }
      final dynamic result = path == '/care/latest' || path.endsWith('/profile')
        ? null : path == '/metrics' || path == '/media/catalog'
        ? {} : path == '/outings/day'
        ? {'moments': [], 'sample_seconds': 0, 'unknown_seconds': 0}
        : path == '/audio-clips/review-queue' ? {'items': []} : [];
      return http.Response(jsonEncode(result), 200);
    });
    await tester.pumpWidget(MaterialApp(home: DashboardPage(client: client)));
    await tester.pump();
    expect(observationRequests, 1);
    await (tester.state(find.byType(DashboardPage)) as dynamic).refresh();
    await tester.drag(find.byType(ListView).first, const Offset(0, -900));
    await tester.pumpAndSettle();
    expect(find.textContaining('관찰 #2 · new'), findsOneWidget);
    firstObservation.complete(http.Response(jsonEncode([{'id': 1, 'source': 'old',
      'observed_at': '2026-10-10T00:00:00Z'}]), 200));
    await tester.pump();
    expect(find.textContaining('관찰 #2 · new'), findsOneWidget);
    expect(find.textContaining('관찰 #1 · old'), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('Genesis dashboard stays usable on a narrow screen', (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final client = MockClient((request) async {
      final path = request.url.path;
      dynamic data;
      if (path == '/outings') {
        data = [{'id': 'outing-1', 'status': 'ended',
          'started_at': '2026-10-11T07:44:04Z', 'input_mode': 'uploaded_audio'}];
      } else if (path.endsWith('/summary') || path == '/outings/day') {
        data = {'moments': [], 'sample_seconds': 0, 'unknown_seconds': 0,
          'bark_candidate_count': 0};
      } else if (path == '/audio-clips/review-queue') {
        data = {'items': []};
      } else if (path == '/care/latest' || path.endsWith('/profile')) {
        data = null;
      } else if (path == '/metrics' || path == '/media/catalog') {
        data = {};
      } else {
        data = [];
      }
      return http.Response(jsonEncode(data), 200,
        headers: {'content-type': 'application/json; charset=utf-8'});
    });
    await tester.pumpWidget(MaterialApp(theme: GenesisTheme.light,
      home: DashboardPage(client: client)));
    await tester.pumpAndSettle();
    expect(find.text('최근 카메라 장면'), findsOneWidget);
    expect(find.text('현재 상태 평가하기'), findsNothing);
    await tester.tap(find.byKey(const ValueKey('nav-1')));
    await tester.pumpAndSettle();
    expect(find.textContaining('10/11 16:44 · 종료 · 음원'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.drag(find.byType(ListView).first, const Offset(0, -500));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });

  testWidgets('empty input is explicit and evaluation disabled', (tester) async {
    tester.view.physicalSize = const Size(1200, 2600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final client = MockClient((request) async {
      final path = request.url.path;
      final dynamic data = path == '/care/latest' || path.endsWith('/profile') ? null : path == '/metrics' || path == '/media/catalog' ? {} : [];
      return http.Response(jsonEncode(data), 200, headers: {'content-type': 'application/json; charset=utf-8'});
    });
    await tester.pumpWidget(MaterialApp(home: DashboardPage(client: client)));
    await tester.pumpAndSettle();
    expect(find.text('데이터 없음'), findsWidgets);
    await tester.tap(find.byKey(const ValueKey('nav-2')));
    await tester.pumpAndSettle();
    final button = tester.widget<FilledButton>(find.ancestor(
      of: find.text('현재 상태 평가하기'), matching: find.byWidgetPredicate((widget) => widget is FilledButton)));
    expect(button.onPressed, isNull);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('scenario creates observation and evaluates its ID then approves', (tester) async {
    tester.view.physicalSize = const Size(1200, 2600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    Map<String, dynamic>? suggestion;
    final observation = {'id': 42, 'source': 'synthetic_demo', 'observed_at': '2026-10-11T00:00:00Z',
      'context': {'motion': {'dominant': 'spinning'}, 'bark': {'count': 8, 'peak_db': -24}}};
    var observed = false;
    var approved = false;
    final client = MockClient((request) async {
      dynamic result;
      final path = request.url.path;
      if (request.method == 'POST' && path == '/demo/observe') {
        expect(jsonDecode(request.body)['scenario'], 'anxious');
        observed = true;
        result = observation;
      } else if (request.method == 'POST' && path == '/care/evaluate') {
        expect(jsonDecode(request.body)['observation_id'], 42);
        suggestion = {'id': 7, 'observation_id': 42, 'summary': '상태를 확인해 주세요.', 'severity': 'attention', 'status': 'pending',
          'provider': 'rule', 'reasons': ['반복 신호'], 'recommended_actions': ['music'],
          'care_steps': ['전후 장면을 확인하고 주변 자극을 기록해 주세요.'],
          'cited_observation_ids': [3], 'retrieval': {'mode': 'mcp', 'status': 'ok',
             'records': [{'id': 3, 'summary': '과거 관찰', 'source': 'user_audio',
               'input_scope': 'public_demo', 'observed_at': '2026-10-10',
               'guardian_feedback': [{'source': 'demo_operator_opinion',
                 'label': 'other', 'note': '공개 시연 확인'}]}],
            'tool_calls': [], 'stats': {'sample_count': 1}}};
        result = suggestion;
      } else if (request.method == 'POST' && path == '/care/7/approve') {
        expect(jsonDecode(request.body)['action_type'], 'music');
        approved = true;
        suggestion!['status'] = 'approved';
        result = {'status': 'requested'};
      } else if (path == '/care/latest') {
        result = suggestion;
      } else if (path.endsWith('/profile')) {
        result = null;
      } else if (path == '/observations') {
        result = observed ? [observation] : [];
      } else if (path == '/metrics' || path == '/media/catalog') {
        result = {};
      } else {
        result = [];
      }
      return http.Response(jsonEncode(result), 200, headers: {'content-type': 'application/json; charset=utf-8'});
    });
    await tester.pumpWidget(MaterialApp(home: DashboardPage(client: client)));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('nav-4')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('회전·짖음 시연'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('nav-2')));
    await tester.pumpAndSettle();
    expect(find.textContaining('#3 · 과거 관찰'), findsOneWidget);
    expect(find.textContaining('기록 #3 시연 담당자 의견: 기타 소리'), findsOneWidget);
    expect(find.textContaining('공개·생성 시연 자료 · 2026-10-10'), findsOneWidget);
    expect(find.text('보호자가 해볼 일'), findsOneWidget);
    expect(find.textContaining('전후 장면을 확인하고 주변 자극을 기록'), findsOneWidget);
    final approval = find.text('가상 음악 실행 승인');
    await tester.ensureVisible(approval);
    await tester.tap(approval);
    await tester.pumpAndSettle();
    expect(approved, isTrue);
    await tester.pumpWidget(const SizedBox());
  });
  group('sustained barking alert', () {
    Map<String, dynamic> alertSuggestion(String status, {String provider = 'sustained-bark-rule'}) => {
      'id': 5, 'pet_id': 'demo-dog', 'observation_id': 1, 'state': 'care_option',
      'summary': '개 짖음 소리 후보가 약 30초 동안 이어지고 있습니다(5초 구간 6개 중 6개).',
      'reasons': ['모델 후보는 실제 짖음의 확정이 아닙니다.'], 'recommended_actions': ['music'], 'music_style': 'calm_piano',
      'severity': 'attention', 'status': status, 'provider': provider, 'context': {}, 'care_steps': [],
      'retrieval': {'records': [], 'stats': {}}, 'cited_observation_ids': [1], 'question': '지속 짖음 알림',
      'created_at': '2026-10-26T08:00:00Z',
    };

    Future<void> open(WidgetTester tester, Map<String, dynamic> suggestion, {String actionMode = 'simulated'}) async {
      tester.view.physicalSize = const Size(1200, 1800);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final client = MockClient((request) async {
        final path = request.url.path;
        final dynamic data = path == '/care/latest' ? suggestion
          : path == '/observations' ? [{'id': 1, 'source': 'live', 'observed_at': '2026-10-26T08:00:00Z', 'context': {}}]
          : path.endsWith('/profile') ? null
          : path == '/health' ? {'components': {'care_provider': 'rule', 'action_mode': actionMode}}
          : path == '/metrics' || path == '/media/catalog' ? {}
          : path == '/outings/day' ? {'moments': [], 'sample_seconds': 0, 'unknown_seconds': 0}
          : path == '/audio-clips/review-queue' ? {'items': []} : [];
        return http.Response.bytes(utf8.encode(jsonEncode(data)), 200);
      });
      await tester.pumpWidget(MaterialApp(home: DashboardPage(client: client)));
      await tester.pumpAndSettle();
    }

    testWidgets('a pending alert is shown on every page and leads to the approval', (tester) async {
      await open(tester, alertSuggestion('pending'));
      expect(find.byKey(const ValueKey('sustained-bark-alert')), findsOneWidget);
      expect(find.textContaining('약 30초 동안 이어지고 있습니다'), findsWidgets);
      await tester.tap(find.byKey(const ValueKey('nav-3')));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('sustained-bark-alert')), findsOneWidget);
      await tester.tap(find.text('원본 확인하고 승인하러 가기'));
      await tester.pumpAndSettle();
      expect(find.text('근거 기반 케어 제안'), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('the approve button says whether the music really plays', (tester) async {
      await open(tester, alertSuggestion('pending'));
      await tester.tap(find.byKey(const ValueKey('nav-2')));
      await tester.pumpAndSettle();
      expect(find.text('가상 음악 실행 승인'), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
      await open(tester, alertSuggestion('pending'), actionMode: 'speaker');
      await tester.tap(find.byKey(const ValueKey('nav-2')));
      await tester.pumpAndSettle();
      expect(find.text('PC 스피커 음악 재생 승인'), findsOneWidget);
      expect(find.text('가상 음악 실행 승인'), findsNothing);
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('no banner once the alert is answered, or for an ordinary suggestion', (tester) async {
      await open(tester, alertSuggestion('approved'));
      expect(find.byKey(const ValueKey('sustained-bark-alert')), findsNothing);
      await tester.pumpWidget(const SizedBox());
      await open(tester, alertSuggestion('pending', provider: 'gemini:gemini-3.5-flash-lite'));
      expect(find.byKey(const ValueKey('sustained-bark-alert')), findsNothing);
      await tester.pumpWidget(const SizedBox());
    });
  });
  group('what the AI received and the answer for the whole outing', () {
    Map<String, dynamic> suggestionWith(Map<String, dynamic> cloudRequest) => {
      'id': 9, 'pet_id': 'demo-dog', 'observation_id': 1, 'state': 'insufficient_observation', 'summary': '기록이 적습니다.',
      'reasons': ['근거 부족'], 'recommended_actions': [], 'music_style': null, 'severity': 'info', 'status': 'informational',
      'provider': 'gemini:test', 'context': {}, 'care_steps': [], 'cited_observation_ids': [], 'question': '짖은 횟수는 몇번?',
      'retrieval': {'records': [], 'stats': {}, 'cloud_request': cloudRequest}, 'created_at': '2026-10-26T08:00:00Z',
    };

    Future<void> pumpRag(WidgetTester tester, Map<String, dynamic> evaluated, {bool outingAnswers = true}) async {
      tester.view.physicalSize = const Size(1200, 2600);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      var evaluatedYet = false; // the server returns the new suggestion as the latest one after an evaluation
      final client = MockClient((request) async {
        final path = request.url.path;
        if (path == '/care/evaluate') evaluatedYet = true;
        final dynamic data = path == '/care/evaluate' ? evaluated
          : path == '/outings/outing-1/explain' ? (outingAnswers ? {'question': '짖은 횟수는 몇번?', 'provider': 'gemini:test:fact-selection',
              'answer': 'YAMNet Bark 분석 창 25개 중 개 짖음 소리 후보 창은 10개입니다. 5초 창은 정확한 발성 횟수가 아닙니다.'} : null)
          : path == '/care/target' ? {'observation_id': 1, 'outing_id': 'outing-1', 'reason': 'latest_candidate', 'observed_at': '2026-10-26T08:00:00Z',
              'window_s': 5.0, 'analyzed_windows': 1, 'dog_candidate_windows': 1}
          : path == '/observations' ? [{'id': 1, 'source': 'live', 'observed_at': '2026-10-26T08:00:00Z', 'context': {}}]
          : path == '/care/latest' ? (evaluatedYet ? evaluated : null)
          : path.endsWith('/profile') ? null
          : path == '/health' ? {'components': {'care_provider': 'gemini', 'action_mode': 'simulated'}}
          : path == '/metrics' || path == '/media/catalog' ? {}
          : path == '/outings/day' ? {'moments': [], 'sample_seconds': 0, 'unknown_seconds': 0}
          : path == '/audio-clips/review-queue' ? {'items': []} : [];
        return http.Response.bytes(utf8.encode(jsonEncode(data)), 200);
      });
      await tester.pumpWidget(MaterialApp(home: DashboardPage(client: client)));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('nav-2')));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField), '짖은 횟수는 몇번?');
      await tester.tap(find.text('현재 상태 평가하기'));
      await tester.pumpAndSettle();
    }

    testWidgets('shows what was sent to the cloud and what was not', (tester) async {
      await pumpRag(tester, suggestionWith({
        'sent': true, 'used_in_answer': true, 'model': 'gemini-test', 'host': 'generativelanguage.googleapis.com',
        'system_instruction': '규칙 문장', 'user_message': '질문과 데이터입니다.', 'record_ids': [4, 6, 5], 'chars': 40,
        'not_sent': ['원본 음원·영상', '접속 키'],
      }));
      expect(find.byKey(const ValueKey('cloud-request')), findsOneWidget);
      expect(find.text('AI(Gemini)에 보낸 내용'), findsOneWidget);
      expect(find.textContaining('찾은 과거 기록 3건(번호 4, 6, 5)'), findsOneWidget);
      expect(find.textContaining('클라우드가 이 PC의 DB나 MCP에 접속한 것이 아닙니다'), findsOneWidget);
      expect(find.textContaining('보내지 않은 것: 원본 음원·영상 · 접속 키'), findsOneWidget);
      await tester.tap(find.text('보낸 전체 내용 보기'));
      await tester.pumpAndSettle();
      expect(find.text('질문과 데이터입니다.'), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('says plainly when nothing went to the cloud', (tester) async {
      await pumpRag(tester, suggestionWith({'sent': false, 'reason': '규칙 제공자가 PC 안에서 만든 제안입니다. 클라우드로 보낸 것이 없습니다.', 'not_sent': ['접속 키']}));
      expect(find.text('클라우드로 보낸 내용 없음'), findsOneWidget);
      expect(find.textContaining('클라우드로 보낸 것이 없습니다'), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('answers the question from the whole outing, next to the suggestion', (tester) async {
      await pumpRag(tester, suggestionWith({'sent': false, 'reason': 'x', 'not_sent': []}));
      expect(find.byKey(const ValueKey('outing-answer')), findsOneWidget);
      expect(find.textContaining('분석 창 25개 중 개 짖음 소리 후보 창은 10개입니다'), findsOneWidget);
      expect(find.textContaining('Gemini는 어떤 사실을 보여 줄지 번호만 골랐습니다'), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('the suggestion still shows when the outing answer is unavailable', (tester) async {
      await pumpRag(tester, suggestionWith({'sent': false, 'reason': 'x', 'not_sent': []}), outingAnswers: false);
      expect(find.byKey(const ValueKey('outing-answer')), findsNothing);
      expect(find.text('근거 기반 케어 제안'), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    });
  });
}
