import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

const String apiBase = String.fromEnvironment(
  'PETMIND_API_BASE',
  defaultValue: 'http://localhost:8000',
);

void main() => runApp(const PetMindApp());

class PetMindApp extends StatelessWidget {
  const PetMindApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'PetMind Care',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xff6750a4),
          brightness: Brightness.dark,
        ),
        scaffoldBackgroundColor: const Color(0xff101018),
        cardTheme: const CardThemeData(color: Color(0xff1c1b24), margin: EdgeInsets.zero),
        useMaterial3: true,
      ),
      home: const DashboardPage(),
    );
  }
}

class DashboardPage extends StatefulWidget {
  const DashboardPage({super.key});

  @override
  State<DashboardPage> createState() => _DashboardPageState();
}

class _DashboardPageState extends State<DashboardPage> {
  Map<String, dynamic>? suggestion;
  Map<String, dynamic>? sensor;
  List<dynamic> actions = const [];
  bool connected = false;
  bool busy = false;
  String notice = '';
  Timer? timer;

  @override
  void initState() {
    super.initState();
    refresh();
    timer = Timer.periodic(const Duration(seconds: 5), (_) => refresh(silent: true));
  }

  @override
  void dispose() {
    timer?.cancel();
    super.dispose();
  }

  Future<dynamic> _get(String path) async {
    final response = await http.get(Uri.parse('$apiBase$path')).timeout(const Duration(seconds: 3));
    if (response.statusCode >= 400) throw Exception(_detail(response));
    if (response.body.isEmpty || response.body == 'null') return null;
    return jsonDecode(utf8.decode(response.bodyBytes));
  }

  Future<dynamic> _post(String path, [Map<String, dynamic>? body]) async {
    final response = await http
        .post(
          Uri.parse('$apiBase$path'),
          headers: {'Content-Type': 'application/json; charset=utf-8'},
          body: jsonEncode(body ?? <String, dynamic>{}),
        )
        .timeout(const Duration(seconds: 5));
    if (response.statusCode >= 400) throw Exception(_detail(response));
    return jsonDecode(utf8.decode(response.bodyBytes));
  }

  String _detail(http.Response response) {
    try {
      final decoded = jsonDecode(utf8.decode(response.bodyBytes));
      return decoded['detail']?.toString() ?? 'HTTP ${response.statusCode}';
    } catch (_) {
      return 'HTTP ${response.statusCode}';
    }
  }

  Future<void> refresh({bool silent = false}) async {
    try {
      final values = await Future.wait([
        _get('/care/latest'),
        _get('/sensors/latest'),
        _get('/care/actions/recent?limit=8'),
      ]);
      if (!mounted) return;
      setState(() {
        suggestion = values[0] as Map<String, dynamic>?;
        sensor = values[1] as Map<String, dynamic>?;
        actions = (values[2] as List<dynamic>?) ?? const [];
        connected = true;
        if (!silent) notice = '최신 상태를 불러왔습니다.';
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        connected = false;
        if (!silent) notice = '서버 연결 실패: $error';
      });
    }
  }

  Future<void> evaluate() async {
    await _run(() async {
      suggestion = await _post('/care/evaluate') as Map<String, dynamic>;
      notice = '새 케어 제안을 생성했습니다.';
      await refresh(silent: true);
    });
  }

  Future<void> approve(String actionType) async {
    final id = suggestion?['id'];
    if (id == null) return;
    await _run(() async {
      final action = await _post('/care/$id/approve', {'action_type': actionType});
      notice = '${_actionName(actionType)} 요청: ${_statusName(action['status'])}';
      await refresh(silent: true);
    });
  }

  Future<void> dismiss() async {
    final id = suggestion?['id'];
    if (id == null) return;
    await _run(() async {
      await _post('/care/$id/dismiss');
      notice = '제안을 거절했습니다.';
      await refresh(silent: true);
    });
  }

  Future<void> _run(Future<void> Function() operation) async {
    if (busy) return;
    setState(() => busy = true);
    try {
      await operation();
    } catch (error) {
      notice = '요청 실패: $error';
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('PetMind Care'),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 16),
            child: Chip(
              avatar: Icon(Icons.circle, size: 12, color: connected ? Colors.green : Colors.red),
              label: Text(connected ? '연결됨' : '연결 끊김'),
            ),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: refresh,
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            _overview(),
            const SizedBox(height: 16),
            _suggestionCard(),
            const SizedBox(height: 16),
            _actionHistory(),
            if (notice.isNotEmpty) ...[
              const SizedBox(height: 12),
              Text(notice, textAlign: TextAlign.center),
            ],
            const SizedBox(height: 12),
            FilledButton.icon(
              onPressed: busy ? null : evaluate,
              icon: busy
                  ? const SizedBox.square(
                      dimension: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.psychology_alt),
              label: const Text('현재 상태 평가하기'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _overview() {
    final careContext = suggestion?['context'] as Map<String, dynamic>? ?? const {};
    final behavior = careContext['observed_behavior']?.toString() ?? '데이터 없음';
    final confidence = ((careContext['behavior_confidence'] as num?) ?? 0) * 100;
    return LayoutBuilder(builder: (_, constraints) {
      final width = constraints.maxWidth >= 760 ? (constraints.maxWidth - 24) / 3 : constraints.maxWidth;
      return Wrap(
        spacing: 12,
        runSpacing: 12,
        children: [
          _metricCard(width, '현재 관찰', behavior, '${confidence.toStringAsFixed(0)}% 시각 신호', Icons.visibility),
          _metricCard(
            width,
            '환경 센서',
            sensor == null ? '데이터 없음' : '${sensor!['temperature'] ?? '-'}°C · ${sensor!['humidity'] ?? '-'}%',
            '사료 잔량 ${sensor?['feed_remaining_g'] ?? '-'}g',
            Icons.sensors,
          ),
          _metricCard(
            width,
            '음성 신호',
            (careContext['bark_detected'] == true) ? '짖음 감지' : '짖음 없음',
            '최근 ${careContext['bark_count'] ?? 0}회',
            Icons.graphic_eq,
          ),
        ],
      );
    });
  }

  Widget _metricCard(double width, String title, String value, String detail, IconData icon) {
    return SizedBox(
      width: width,
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(children: [
            Icon(icon, size: 34, color: Theme.of(context).colorScheme.primary),
            const SizedBox(width: 14),
            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(title, style: Theme.of(context).textTheme.labelLarge),
              const SizedBox(height: 4),
              Text(value, style: Theme.of(context).textTheme.titleLarge),
              Text(detail, style: Theme.of(context).textTheme.bodySmall),
            ])),
          ]),
        ),
      ),
    );
  }

  Widget _suggestionCard() {
    if (suggestion == null) {
      return const Card(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: Text('아직 생성된 케어 제안이 없습니다. 현재 상태 평가를 실행하세요.'),
        ),
      );
    }
    final reasons = suggestion!['reasons'] as List<dynamic>? ?? const [];
    final recommended = suggestion!['recommended_actions'] as List<dynamic>? ?? const [];
    final pending = const {'pending', 'partially_approved', 'action_failed'}
        .contains(suggestion!['status']);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            const Icon(Icons.auto_awesome),
            const SizedBox(width: 8),
            Expanded(child: Text('AI 케어 제안', style: Theme.of(context).textTheme.titleLarge)),
            Chip(label: Text(_severityName(suggestion!['severity']?.toString()))),
          ]),
          const SizedBox(height: 14),
          Text(suggestion!['summary']?.toString() ?? '-', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 12),
          Text('판단 근거', style: Theme.of(context).textTheme.labelLarge),
          ...reasons.map((reason) => Padding(
                padding: const EdgeInsets.only(top: 5),
                child: Text('• $reason'),
              )),
          const SizedBox(height: 16),
          Text('제안 상태: ${_statusName(suggestion!['status'])} · 제공자: ${_providerName(suggestion!['provider'])}'),
          if (pending && recommended.isNotEmpty) ...[
            const SizedBox(height: 16),
            Wrap(spacing: 8, runSpacing: 8, children: [
              for (final action in recommended)
                FilledButton.icon(
                  onPressed: busy ? null : () => approve(action.toString()),
                  icon: Icon(action == 'feeding' ? Icons.restaurant : Icons.music_note),
                  label: Text('${_actionName(action.toString())} 승인'),
                ),
              OutlinedButton(onPressed: busy ? null : dismiss, child: const Text('거절')),
            ]),
          ],
        ]),
      ),
    );
  }

  Widget _actionHistory() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('최근 실행 이력', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 8),
          if (actions.isEmpty) const Text('실행 이력이 없습니다.'),
          for (final item in actions)
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: Icon(item['action_type'] == 'feeding' ? Icons.restaurant : Icons.music_note),
              title: Text(_actionName(item['action_type']?.toString() ?? '')),
              subtitle: Text(item['error']?.toString() ?? item['command_id']?.toString() ?? ''),
              trailing: Chip(label: Text(_statusName(item['status']))),
            ),
        ]),
      ),
    );
  }

  String _actionName(String value) => value == 'feeding' ? '급식' : value == 'music' ? '음악 재생' : value;

  String _providerName(dynamic value) {
    final name = value?.toString() ?? '';
    if (name.startsWith('gemini:')) return 'Gemini AI';
    if (name == 'rule-fallback') return '기본 판단(대체 동작)';
    if (name == 'rule') return '기본 케어 판단';
    return name;
  }

  String _severityName(String? value) => const {
        'info': '정상',
        'attention': '관찰 필요',
        'warning': '주의',
        'urgent': '긴급',
      }[value] ?? value ?? '-';

  String _statusName(dynamic value) => const {
        'pending': '승인 대기',
        'informational': '정보',
        'approved': '승인됨',
        'partially_approved': '일부 승인됨',
        'dismissed': '거절됨',
        'partially_dismissed': '나머지 거절됨',
        'requested': '실행 요청',
        'acknowledged': '장치 확인',
        'completed': '완료',
        'failed': '실패',
        'action_failed': '실행 실패',
      }[value] ?? value?.toString() ?? '-';
}
