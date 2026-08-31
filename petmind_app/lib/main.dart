import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

const String kApiBase = 'http://localhost:8000';

const Map<String, Color> kBehaviorColor = {
  'happy':   Color(0xFF4CAF50),
  'anxious': Color(0xFFFF9800),
  'playing': Color(0xFF2196F3),
  'resting': Color(0xFF9E9E9E),
  'alert':   Color(0xFFF44336),
};

const Map<String, String> kBehaviorEmoji = {
  'happy':   '😊',
  'anxious': '😟',
  'playing': '🎾',
  'resting': '😴',
  'alert':   '⚠️',
};

const Map<String, String> kEmotionEmoji = {
  'happy':   '😄',
  'sad':     '😢',
  'angry':   '😠',
  'neutral': '😐',
};

void main() {
  runApp(const PetMindApp());
}

class PetMindApp extends StatelessWidget {
  const PetMindApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'PetMind',
      debugShowCheckedModeBanner: false,
      theme: ThemeData.dark().copyWith(
        scaffoldBackgroundColor: const Color(0xFF13131F),
        colorScheme: ColorScheme.dark(
          primary: const Color(0xFF4CAF50),
          surface: const Color(0xFF1E1E2E),
        ),
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
  List<Map<String, dynamic>> _analysis = [];
  List<Map<String, dynamic>> _feeding  = [];
  bool _connected = false;
  int  _feedAmount = 50;
  bool _feeding_busy = false;
  String _statusMsg = '';
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _refresh();
    _timer = Timer.periodic(const Duration(seconds: 5), (_) => _refresh());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _refresh() async {
    await Future.wait([_fetchAnalysis(), _fetchFeeding()]);
  }

  Future<void> _fetchAnalysis() async {
    try {
      final r = await http
          .get(Uri.parse('$kApiBase/analysis/?limit=20'))
          .timeout(const Duration(seconds: 3));
      if (r.statusCode == 200) {
        setState(() {
          _analysis  = List<Map<String, dynamic>>.from(jsonDecode(r.body));
          _connected = true;
        });
      }
    } catch (_) {
      setState(() => _connected = false);
    }
  }

  Future<void> _fetchFeeding() async {
    try {
      final r = await http
          .get(Uri.parse('$kApiBase/feeding/?limit=20'))
          .timeout(const Duration(seconds: 3));
      if (r.statusCode == 200) {
        setState(() {
          _feeding = List<Map<String, dynamic>>.from(jsonDecode(r.body));
        });
      }
    } catch (_) {}
  }

  Future<void> _doFeed() async {
    setState(() => _feeding_busy = true);
    try {
      final r = await http
          .post(
            Uri.parse('$kApiBase/feeding/'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'amount_g': _feedAmount, 'triggered_by': 'manual'}),
          )
          .timeout(const Duration(seconds: 5));
      if (r.statusCode == 200) {
        setState(() => _statusMsg = '✅ 급식 완료: $_feedAmount g');
        await _refresh();
      } else {
        setState(() => _statusMsg = '❌ 서버 오류: ${r.statusCode}');
      }
    } catch (e) {
      setState(() => _statusMsg = '❌ 연결 실패: $e');
    } finally {
      setState(() => _feeding_busy = false);
    }
  }

  int get _todayFeedCount {
    final today = DateTime.now().toUtc().toIso8601String().substring(0, 10);
    return _feeding.where((d) => (d['timestamp'] as String).startsWith(today)).length;
  }

  Map<String, dynamic>? get _latest => _analysis.isNotEmpty ? _analysis.first : null;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _buildHeader(),
              const SizedBox(height: 16),
              _buildCards(),
              const SizedBox(height: 16),
              _buildFeedControl(),
              if (_statusMsg.isNotEmpty) ...[
                const SizedBox(height: 8),
                Text(_statusMsg, style: const TextStyle(color: Color(0xFF9E9E9E), fontSize: 13)),
              ],
              const SizedBox(height: 16),
              Expanded(child: _buildTables()),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildHeader() {
    return Row(
      children: [
        const Text('🐾 PetMind', style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
        const Spacer(),
        Container(
          width: 10, height: 10,
          decoration: BoxDecoration(
            color: _connected ? const Color(0xFF4CAF50) : const Color(0xFFF44336),
            shape: BoxShape.circle,
          ),
        ),
        const SizedBox(width: 6),
        Text(
          _connected ? '연결됨' : '연결 끊김',
          style: TextStyle(
            color: _connected ? const Color(0xFF4CAF50) : const Color(0xFFF44336),
            fontSize: 13,
          ),
        ),
      ],
    );
  }

  Widget _buildCards() {
    final b = _latest?['behavior'] as String?;
    final e = _latest?['emotion']  as String?;
    final bc = _latest?['behavior_conf'] as double? ?? 0;
    final ec = _latest?['emotion_conf']  as double? ?? 0;

    return Row(
      children: [
        Expanded(child: _StatusCard(
          title: '행동 인식',
          value: b != null ? '${kBehaviorEmoji[b] ?? ''} $b' : '—',
          sub: b != null ? '${(bc * 100).toStringAsFixed(0)}%' : '',
          color: b != null ? (kBehaviorColor[b] ?? Colors.white) : Colors.white,
        )),
        const SizedBox(width: 12),
        Expanded(child: _StatusCard(
          title: '감정 분석',
          value: e != null ? '${kEmotionEmoji[e] ?? ''} $e' : '—',
          sub: e != null ? '${(ec * 100).toStringAsFixed(0)}%' : '',
          color: const Color(0xFF64B5F6),
        )),
        const SizedBox(width: 12),
        Expanded(child: _StatusCard(
          title: '오늘 급식',
          value: '${_todayFeedCount}회',
          sub: '',
          color: const Color(0xFFFFB74D),
        )),
      ],
    );
  }

  Widget _buildFeedControl() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        color: const Color(0xFF1E1E2E),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: const Color(0xFF333344)),
      ),
      child: Row(
        children: [
          const Text('급식량 (g): ', style: TextStyle(fontSize: 14)),
          const SizedBox(width: 8),
          IconButton(
            onPressed: () => setState(() => _feedAmount = (_feedAmount - 10).clamp(10, 200)),
            icon: const Icon(Icons.remove_circle_outline),
            color: Colors.white70,
          ),
          Text('$_feedAmount', style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
          IconButton(
            onPressed: () => setState(() => _feedAmount = (_feedAmount + 10).clamp(10, 200)),
            icon: const Icon(Icons.add_circle_outline),
            color: Colors.white70,
          ),
          const Spacer(),
          ElevatedButton.icon(
            onPressed: _feeding_busy ? null : _doFeed,
            icon: _feeding_busy
                ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                : const Text('🍽️'),
            label: const Text('급식 실행'),
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFF4CAF50),
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTables() {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(child: _buildAnalysisTable()),
        const SizedBox(width: 12),
        Expanded(child: _buildFeedingTable()),
      ],
    );
  }

  Widget _buildAnalysisTable() {
    return _TableCard(
      title: '분석 기록 (최근 20건)',
      headers: const ['시간', '행동', '감정'],
      rows: _analysis.map((row) {
        final ts = (row['timestamp'] as String).substring(0, 19).replaceFirst('T', ' ');
        final b  = row['behavior'] as String;
        final e  = row['emotion']  as String;
        return [
          _TableCell(text: ts),
          _TableCell(text: '${kBehaviorEmoji[b] ?? ''} $b', color: kBehaviorColor[b]),
          _TableCell(text: '${kEmotionEmoji[e] ?? ''} $e'),
        ];
      }).toList(),
    );
  }

  Widget _buildFeedingTable() {
    return _TableCard(
      title: '급식 기록 (최근 20건)',
      headers: const ['시간', '급식량', '구분'],
      rows: _feeding.map((row) {
        final ts = (row['timestamp'] as String).substring(0, 19).replaceFirst('T', ' ');
        return [
          _TableCell(text: ts),
          _TableCell(text: '${row['amount_g']}g'),
          _TableCell(text: row['triggered_by'] as String),
        ];
      }).toList(),
    );
  }
}

class _StatusCard extends StatelessWidget {
  final String title, value, sub;
  final Color color;
  const _StatusCard({required this.title, required this.value, required this.sub, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 12),
      decoration: BoxDecoration(
        color: const Color(0xFF1E1E2E),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        children: [
          Text(title, style: const TextStyle(color: Color(0xFF888888), fontSize: 12)),
          const SizedBox(height: 8),
          Text(value, style: TextStyle(color: color, fontSize: 20, fontWeight: FontWeight.bold)),
          if (sub.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(sub, style: const TextStyle(color: Color(0xFFAAAAAA), fontSize: 12)),
          ],
        ],
      ),
    );
  }
}

class _TableCell {
  final String text;
  final Color? color;
  _TableCell({required this.text, this.color});
}

class _TableCard extends StatelessWidget {
  final String title;
  final List<String> headers;
  final List<List<_TableCell>> rows;
  const _TableCard({required this.title, required this.headers, required this.rows});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF1E1E2E),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: const Color(0xFF333344)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 10, 12, 6),
            child: Text(title, style: const TextStyle(color: Color(0xFFCCCCCC), fontSize: 13)),
          ),
          const Divider(color: Color(0xFF333344), height: 1),
          // 헤더
          Container(
            color: const Color(0xFF2A2A3E),
            child: Row(
              children: headers
                  .map((h) => Expanded(
                        child: Padding(
                          padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 8),
                          child: Text(h, style: const TextStyle(color: Color(0xFFCCCCCC), fontSize: 12)),
                        ),
                      ))
                  .toList(),
            ),
          ),
          // 데이터 행
          ...rows.asMap().entries.map((entry) {
            final odd = entry.key.isOdd;
            return Container(
              color: odd ? const Color(0xFF252535) : Colors.transparent,
              child: Row(
                children: entry.value
                    .map((cell) => Expanded(
                          child: Padding(
                            padding: const EdgeInsets.symmetric(vertical: 5, horizontal: 8),
                            child: Text(
                              cell.text,
                              style: TextStyle(
                                color: cell.color ?? const Color(0xFFEEEEEE),
                                fontSize: 12,
                              ),
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                        ))
                    .toList(),
              ),
            );
          }),
        ],
      ),
    );
  }
}
