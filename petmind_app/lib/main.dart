import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:http/http.dart' as http;
import 'genesis_theme.dart';
import 'outings_panel.dart';
import 'camera_panel.dart';

const String apiBase = String.fromEnvironment(
  'PETMIND_API_BASE',
  defaultValue: 'http://localhost:8010',
);
const bool yamnetTrial = bool.fromEnvironment('PETMIND_YAMNET_TRIAL', defaultValue: false);

void main() {
  runApp(const PetMindApp());
  if (kIsWeb) SemanticsBinding.instance.ensureSemantics();
}

class PetMindApp extends StatelessWidget {
  const PetMindApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: yamnetTrial ? 'PetMind YAMNet + RAG 시험' : 'PetMind Care',
      debugShowCheckedModeBanner: false,
      theme: GenesisTheme.light,
      home: const DashboardPage(),
    );
  }
}

class DashboardPage extends StatefulWidget {
  const DashboardPage({super.key, this.client, this.previewProvider, this.initialPetId = 'demo-dog'});
  final http.Client? client;
  final ImageProvider? previewProvider;
  final String initialPetId;

  @override
  State<DashboardPage> createState() => _DashboardPageState();
}

class _DashboardPageState extends State<DashboardPage> {
  Map<String, dynamic>? suggestion;
  Map<String, dynamic>? observation;
  Map<String, dynamic>? profile;
  Map<String, dynamic>? savedFeedback;
  Map<String, dynamic>? baseline;
  Map<String, dynamic>? comparison;
  Map<String, dynamic>? activeOuting;
  Map<String, dynamic> metrics = {};
  List<dynamic> timeline = const [];
  Map<String, dynamic> catalog = {};
  Map<String, dynamic>? mediaResult;
  String? audioFilename;
  bool includeVideo = true;
  String petId = 'demo-dog';
  final question = TextEditingController(text: '최근 기록과 비교해서 어떤 케어가 필요할까요?');
  late final http.Client client;
  List<dynamic> actions = const [];
  bool connected = false;
  String careProvider = 'unknown';
  int section = 0;
  static const sectionNames = ['홈', '외출·음원', 'RAG·케어', '기록', '설정·시연'];
  static const sectionIcons = [Icons.home_outlined, Icons.mic_none,
    Icons.forum_outlined, Icons.history, Icons.settings_outlined];
  bool busy = false;
  String? connectionIssue;
  List<String> _optionalFailures = const [];
  bool _refreshing = false;
  int _refreshSequence = 0;
  String notice = '';
  Timer? timer;

  @override
  void initState() {
    super.initState();
    petId = widget.initialPetId;
    client = widget.client ?? http.Client();
    refresh();
    timer = Timer.periodic(const Duration(seconds: 15), (_) {
      if (!busy && !_refreshing) refresh(silent: true);
    });
  }

  @override
  void dispose() {
    timer?.cancel();
    question.dispose();
    client.close();
    super.dispose();
  }

  Future<dynamic> _get(String path) async {
    final response = await client.get(Uri.parse('$apiBase$path')).timeout(const Duration(seconds: 5));
    if (response.statusCode >= 400) throw Exception(_detail(response));
    if (response.body.isEmpty || response.body == 'null') return null;
    return jsonDecode(utf8.decode(response.bodyBytes));
  }

  Future<dynamic> _post(String path, [Map<String, dynamic>? body]) async {
    final response = await client
        .post(
          Uri.parse('$apiBase$path'),
          headers: {'Content-Type': 'application/json; charset=utf-8'},
          body: jsonEncode(body ?? <String, dynamic>{}),
        )
        .timeout(const Duration(seconds: 35));
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
    final sequence = ++_refreshSequence;
    _refreshing = true;
    final requestedPet = petId;
    final petQuery = Uri.encodeQueryComponent(requestedPet);
    final petPath = Uri.encodeComponent(requestedPet);
    final optionalFailures = <String>[];
    try {
      final values = await Future.wait([
        _get('/care/latest?pet_id=$petQuery'),
        _get('/observations?pet_id=$petQuery&limit=1'),
        _get('/care/actions/recent?pet_id=$petQuery&limit=8').catchError((Object _) {
          optionalFailures.add('최근 실행');
          return actions;
        }),
        _get('/timeline?pet_id=$petQuery').catchError((Object _) {
          optionalFailures.add('처리 타임라인');
          return timeline;
        }),
        _get('/metrics?pet_id=$petQuery').catchError((Object _) {
          optionalFailures.add('집계 지표');
          return metrics;
        }),
        if (silent) Future<dynamic>.value(catalog) else
          _get('/media/catalog').catchError((Object _) {
            optionalFailures.add('공개 자료 목록');
            return catalog;
          }),
        if (silent) Future<dynamic>.value(profile) else
          _get('/pets/$petPath/profile').catchError((Object _) {
            optionalFailures.add('프로필');
            return profile;
          }),
        if (yamnetTrial) _get('/health').catchError((Object _) => null)
          else Future<dynamic>.value(null),
      ]);
      if (!mounted || sequence != _refreshSequence || requestedPet != petId) return;
      setState(() {
        suggestion = values[0] as Map<String, dynamic>?;
        final observations = values[1] as List<dynamic>;
        observation = observations.isEmpty ? null : observations.first as Map<String, dynamic>;
        actions = (values[2] as List<dynamic>?) ?? const [];
        timeline = values[3] as List<dynamic>;
        metrics = values[4] as Map<String, dynamic>;
        catalog = values[5] as Map<String, dynamic>;
        final audioFiles = (catalog['files'] as List<dynamic>? ?? const []).where((file) => file['type'] == 'audio');
        audioFilename ??= audioFiles.isEmpty ? null : audioFiles.first['filename'].toString();
        profile = values[6] as Map<String, dynamic>?;
        careProvider = (values[7] as Map<String, dynamic>?)?['components']?['care_provider']?.toString() ?? 'unknown';
        connected = true;
        if (!silent) _optionalFailures = optionalFailures;
        connectionIssue = _optionalFailures.isEmpty ? null
          : '${_optionalFailures.join('·')}을 불러오지 못했습니다. 핵심 관찰 기록은 표시 중입니다.';
        if (!silent) notice = connectionIssue ?? '최신 상태를 불러왔습니다.';
      });
    } catch (_) {
      if (!mounted || sequence != _refreshSequence || requestedPet != petId) return;
      setState(() {
        connected = false;
        connectionIssue = '서버에 연결할 수 없습니다. 백엔드 실행을 확인한 뒤 다시 연결해 주세요.';
        notice = '';
      });
    } finally {
      if (sequence == _refreshSequence) _refreshing = false;
    }
  }

  Future<void> evaluate() async {
    if (observation == null) return;
    await _run(() async {
      suggestion = await _post('/care/evaluate', {
        'observation_id': observation!['id'], 'question': question.text,
      }) as Map<String, dynamic>;
      notice = '새 케어 제안을 생성했습니다.';
      await refresh(silent: true);
    });
  }

  Future<void> demo(String scenario) async {
    if (activeOuting != null && activeOuting!['input_mode'] != 'synthetic_demo') {
      setState(() => notice = '진행 중 외출은 ${_inputModeName(activeOuting!['input_mode'])} 모드입니다. 합성 시연을 사용하려면 외출을 종료해 주세요.');
      return;
    }
    await _run(() async {
      observation = await _post('/demo/observe', {'pet_id': petId, 'scenario': scenario,
        if (activeOuting != null) 'outing_id': activeOuting!['id']}) as Map<String, dynamic>;
      suggestion = await _post('/care/evaluate', {
        'observation_id': observation!['id'], 'question': question.text,
      }) as Map<String, dynamic>;
      await refresh(silent: true);
      notice = '합성 시나리오 분석·저장·제안 생성 완료';
    });
  }

  Future<void> seedHistory() async {
    await _run(() async {
      final result = await _post('/demo/seed', {'pet_id': petId});
      await refresh(silent: true);
      notice = '합성 과거 기록 ${result['created']}건 추가';
    });
  }

  Future<void> analyzePublicMedia() async {
    if (audioFilename == null) return;
    if (activeOuting != null && activeOuting!['input_mode'] != 'prepared_video') {
      setState(() => notice = '진행 중 외출은 ${_inputModeName(activeOuting!['input_mode'])} 모드입니다. 준비된 영상·음원을 사용하려면 외출을 종료해 주세요.');
      return;
    }
    await _run(() async {
      mediaResult = await _post('/media/observe', {
        'pet_id': petId, 'audio_filename': audioFilename,
        'include_video': includeVideo && catalog['video_prepared'] == true,
        if (activeOuting != null) 'outing_id': activeOuting!['id'],
      }) as Map<String, dynamic>;
      observation = mediaResult!['observation'] as Map<String, dynamic>;
      suggestion = await _post('/care/evaluate', {
        'observation_id': observation!['id'], 'question': question.text,
      }) as Map<String, dynamic>;
      await refresh(silent: true);
      notice = '공개 입력 분석·저장·제안 생성 완료';
    });
  }

  Future<void> editProfile() async {
    final data = await showDialog<Map<String, dynamic>>(context: context,
      builder: (_) => ProfileEditor(profile: profile));
    if (data == null || !mounted) return;
    await _run(() async {
      profile = await _post('/pets/$petId/profile', data) as Map<String, dynamic>;
      notice = '보호자 입력 프로필을 저장했습니다. 다음 평가에 반영됩니다.';
    });
  }

  Future<void> recordFeedback() async {
    final observationId = suggestion?['observation_id'];
    final suggestionId = suggestion?['id'];
    if (observationId == null || suggestionId == null) return;
    final data = await showDialog<Map<String, dynamic>>(context: context,
      builder: (_) => const FeedbackEditor());
    if (data == null || !mounted) return;
    await _run(() async {
      savedFeedback = await _post('/feedback', {'observation_id': observationId,
        'suggestion_id': suggestionId, ...data}) as Map<String, dynamic>;
      notice = '보호자 피드백을 저장했습니다. 자동 학습 정답으로 사용하지 않습니다.';
    });
  }

  Future<void> loadBaseline() async {
    if (observation == null) return;
    await _run(() async {
      baseline = await _get('/pets/$petId/baseline?observation_id=${observation!['id']}') as Map<String, dynamic>;
    });
  }

  Future<void> loadComparison(String commandId) async {
    await _run(() async {
      comparison = await _get('/care/actions/$commandId/comparison') as Map<String, dynamic>;
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
        title: LayoutBuilder(builder: (context, constraints) => Row(
          mainAxisSize: MainAxisSize.min, children: [
            const Text('PetMind', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700,
              letterSpacing: -0.4)),
            if (constraints.maxWidth >= 340) ...[
              const SizedBox(width: 12),
              Flexible(child: Text(yamnetTrial ? 'YAMNET + RAG / 시험' : 'CARE / EVIDENCE', maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.labelSmall?.copyWith(
                  color: GenesisTheme.secondaryInk, letterSpacing: 1.1))),
            ],
          ],
        )),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 16),
            child: Center(child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(color: const Color(0xFFF4F4F5),
                borderRadius: BorderRadius.circular(999)),
              child: Row(mainAxisSize: MainAxisSize.min, children: [
                Icon(Icons.circle, size: 12,
                  color: connected ? GenesisTheme.success : GenesisTheme.error),
                const SizedBox(width: 8),
                Text(connected ? '연결됨' : '연결 끊김', softWrap: false,
                  style: Theme.of(context).textTheme.labelMedium),
              ]),
            )),
          ),
        ],
      ),
      body: Column(children: [
        Padding(padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          child: Wrap(spacing: 8, runSpacing: 8, children: [
            for (var i = 0; i < sectionNames.length; i++) ChoiceChip(
              key: ValueKey('nav-$i'),
              avatar: Icon(sectionIcons[i], size: 18),
              label: Text(sectionNames[i]), selected: section == i,
              onSelected: (_) {
                setState(() => section = i);
                if (i == 2) refresh(silent: true);
              },
            ),
          ])),
        Expanded(child: IndexedStack(index: section, children: [
          _sectionPage(0, [
            _pageIntro(),
            _overview(),
            if (activeOuting?['input_mode'] == 'live') Text('자동 외출 · ${activeOuting?['capture_label'] ?? '장치 상태 확인 중'}'),
            if (observation != null) Text('관찰 #${observation!['id']} · ${observation!['source']} · ${observation!['observed_at']}'),
            if (section == 0) const CameraPanel(base: apiBase),
            Wrap(spacing: 12, runSpacing: 8, children: [
              OutlinedButton(onPressed: () => setState(() => section = 1), child: const Text('외출 기록·음원 분석으로')),
              OutlinedButton(onPressed: () => setState(() => section = 2), child: const Text('근거 질문·케어로')),
            ]),
          ]),
          _sectionPage(1, [
            _sectionTitle('외출 기록과 음원 분석', '외출 시작, 음원 입력, 보호자 확인과 귀가 요약을 관리합니다.'),
            OutingsPanel(client: client, base: apiBase, petId: petId,
              observationId: observation?['id'] as int?,
              onActiveChanged: (value) { if (mounted) setState(() => activeOuting = value); }),
          ]),
          _sectionPage(2, [
            _sectionTitle('RAG 질문과 케어', '저장된 관찰과 보호자 의견을 근거로 제안을 검토합니다.'),
            if (yamnetTrial) Text(careProvider == 'gemini'
              ? '이 비교 사이트는 로컬 기록을 검색하고 Gemini 생성 답변을 시도합니다. 실제 사용 여부는 아래 제안의 제공자 표시로 확인하세요.'
              : '이 비교 사이트는 로컬 기록 검색과 규칙 기반 케어 제안을 사용합니다. Gemini 생성 답변은 현재 실행하지 않습니다.'),
            TextField(controller: question, decoration: const InputDecoration(labelText: '기록에 대해 질문하기'), maxLength: 1000),
            FilledButton.icon(onPressed: busy || observation == null ? null : evaluate,
              icon: const Icon(Icons.psychology_alt), label: const Text('현재 상태 평가하기')),
            _suggestionCard(), _evidenceCard(), _comparisonCard(),
          ]),
          _sectionPage(3, [
            _sectionTitle('처리 기록', '관찰·제안·승인 이력을 확인합니다.'),
            _timelineCard(), _actionHistory(),
          ]),
          _sectionPage(4, [
            _sectionTitle('반려견 설정과 시연', '프로필을 관리하고 별도로 표시된 시연 자료를 사용합니다.'),
            _inputCard(), _mediaCard(),
          ]),
        ])),
      ]),
    );
  }

  Widget _sectionPage(int index, List<Widget> children) => RefreshIndicator(
    onRefresh: refresh,
    child: Center(child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: 1280),
      child: ListView(key: PageStorageKey('section-$index'),
        padding: const EdgeInsets.all(24), children: [
          if (connectionIssue != null) ...[_connectionBanner(), const SizedBox(height: 16)],
          for (final child in children) ...[child, const SizedBox(height: 20)],
          if (notice.isNotEmpty) Text(notice),
        ]))),
  );

  Widget _pageIntro() => LayoutBuilder(builder: (context, constraints) {
    final compact = constraints.maxWidth < 640;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text('PETMIND / CARE JOURNAL', style: Theme.of(context).textTheme.labelSmall?.copyWith(
        color: GenesisTheme.secondaryInk, letterSpacing: 1.6, fontWeight: FontWeight.w700)),
      const SizedBox(height: 12),
      Text('반려견의 하루를, 근거로 확인하세요.',
        style: Theme.of(context).textTheme.headlineMedium?.copyWith(fontSize: compact ? 29 : 38)),
      const SizedBox(height: 12),
      Text('영상과 소리의 관찰 신호를 기록하고, 보호자 의견과 과거 근거를 함께 살펴봅니다.',
        style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: GenesisTheme.secondaryInk)),
    ]);
  });

  Widget _connectionBanner() => Container(
    width: double.infinity,
    padding: const EdgeInsets.all(16),
    decoration: BoxDecoration(
      color: const Color(0xFFFFF7E6),
      border: Border.all(color: const Color(0xFFF0DCA8)),
      borderRadius: BorderRadius.circular(8),
    ),
    child: Wrap(spacing: 12, runSpacing: 8,
      crossAxisAlignment: WrapCrossAlignment.center, children: [
        Icon(connected ? Icons.info_outline : Icons.cloud_off_outlined,
          color: GenesisTheme.warningInk),
        Text(connectionIssue!, style: Theme.of(context).textTheme.bodyMedium),
        OutlinedButton(onPressed: () => refresh(), child: const Text('다시 연결')),
      ]),
  );

  Widget _sectionTitle(String title, String description) => Column(
    crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(title, style: Theme.of(context).textTheme.titleLarge),
      const SizedBox(height: 4),
      Text(description, style: Theme.of(context).textTheme.bodySmall),
    ],
  );

  Widget _inputCard() {
    return Card(child: Padding(padding: const EdgeInsets.all(20), child: Column(
      crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('관찰 입력과 시연', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 8),
        const Text('아래 시나리오는 합성 영상 좌표·음성입니다. 가상 장치는 실제 소리를 재생하지 않습니다.'),
        const SizedBox(height: 12),
        DropdownButton<String>(
          value: petId,
          items: [
            const DropdownMenuItem(value: 'demo-dog', child: Text('시연 반려견 A')),
            const DropdownMenuItem(value: 'demo-dog-2', child: Text('시연 반려견 B')),
            if (!const {'demo-dog', 'demo-dog-2'}.contains(widget.initialPetId))
              DropdownMenuItem(value: widget.initialPetId, child: const Text('현재 반려견')),
          ],
          onChanged: busy ? null : (value) {
            if (value == null) return;
            setState(() {
              petId = value; observation = null; suggestion = null;
              actions = const []; timeline = const []; metrics = {}; mediaResult = null; profile = null;
              savedFeedback = null; baseline = null; comparison = null; activeOuting = null;
            });
            refresh();
          },
        ),
        Wrap(spacing: 12, runSpacing: 4, crossAxisAlignment: WrapCrossAlignment.center, children: [
          Text(profile == null ? '프로필 미등록' : '${profile!['name']} · ${profile!['age_years'] ?? '-'}세 · 보호자 입력'),
          TextButton(onPressed: busy ? null : editProfile, child: const Text('프로필·메모 편집')),
        ]),
        const SizedBox(height: 12),
        Wrap(spacing: 8, runSpacing: 8, children: [
          OutlinedButton(onPressed: busy ? null : seedHistory, child: const Text('합성 과거 기록 준비')),
          OutlinedButton(onPressed: busy ? null : () => demo('calm'), child: const Text('휴식 시연')),
          OutlinedButton(onPressed: busy ? null : () => demo('anxious'), child: const Text('회전·짖음 시연')),
          OutlinedButton(onPressed: busy ? null : () => demo('bored_pacing'), child: const Text('왕복 이동 시연')),
        ]),
        if (observation != null) Padding(padding: const EdgeInsets.only(top: 12),
          child: Text('관찰 #${observation!['id']} · ${observation!['source']} · ${observation!['observed_at']}')),
      ],
    )));
  }

  Widget _evidenceCard() {
    final evidence = suggestion?['retrieval'] as Map<String, dynamic>?;
    final currentAudio = evidence?['current_audio'] as Map<String, dynamic>?;
    final frequency = evidence?['frequency_comparison'] as Map<String, dynamic>?;
    final plan = evidence?['query_plan'] as Map<String, dynamic>?;
    final search = evidence?['search'] as Map<String, dynamic>?;
    final records = evidence?['records'] as List<dynamic>? ?? const [];
    final calls = evidence?['tool_calls'] as List<dynamic>? ?? const [];
    return Card(child: Padding(padding: const EdgeInsets.all(20), child: Column(
      crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('개별 기록 검색 근거', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 8),
        Text(evidence == null ? '제안을 생성하면 검색 근거가 표시됩니다.'
          : '조회 방식: ${evidence['mode']} · 상태: ${evidence['status']} · 인용 ${suggestion!['cited_observation_ids']}'),
        if (currentAudio != null) ...[
          const SizedBox(height: 8),
          Text('이번 관찰 #${currentAudio['observation_id']} · ${currentAudio['input_scope'] == 'public_demo' ? '공개·생성 시연 자료' : '사용자 음원'}'),
          Text('${currentAudio['model_name'] ?? 'LSTM'}: 분석 창 ${currentAudio['analyzed_windows']}개 중 개 짖음 소리 후보 ${currentAudio['dog_candidate_windows']}개'),
          Text('${currentAudio['input_scope'] == 'public_demo' || currentAudio['review_source'] == 'demo_operator_opinion' ? '시연 담당자' : '보호자'} 확인 의견: ${_audioReviewName(currentAudio['review_label']?.toString())}'),
          const Text('5초 창은 실제 짖음 횟수가 아니며, 확인 의견도 정답 라벨은 아닙니다.'),
        ],
        if (evidence?['status'] == 'failed') const Text('기록 검색 실패: 현재 관찰만으로 제안했습니다.'),
        if (evidence?['status'] == 'ok' && records.isEmpty) const Text('선택 기간과 질문에 맞는 과거 근거가 없습니다.'),
        if (plan != null) Text('검색 기간: ${plan['start']}Z ~ ${plan['before']}Z · 한국 시간 해석'),
        if (search != null) Text(search['method'] == 'hybrid_gemini_embedding_001'
          ? '키워드 + 의미 검색으로 근거를 찾았습니다.' : search['method'] == 'recent_context'
          ? '최근 관찰 기록을 시간순으로 조회했습니다.' : '키워드 검색으로 근거를 찾았습니다.'),
        if (search?['embedding_failure'] != null) const Text('의미 검색 연결 실패로 키워드 검색을 사용했습니다.'),
        if (search?['recency_context_only'] == true) const Text('최신 배경 기록이며 특정 질문의 직접 증거는 아닙니다.'),
        for (final call in calls) Text('${call['tool']} → ${call['status']}'),
        for (final record in records) ListTile(
          contentPadding: EdgeInsets.zero,
          title: Text('#${record['id']} · ${record['summary']}'),
          subtitle: Text('${record['input_scope'] == 'public_demo' ? '공개·생성 시연 자료' : record['source']} · ${record['observed_at']}'),
        ),
        for (final record in records)
          for (final feedback in (record['guardian_feedback'] as List<dynamic>? ?? const []))
            Text('기록 #${record['id']} ${feedback['source'] == 'demo_operator_opinion' ? '시연 담당자 의견' : '보호자 의견'}: ${feedback['label'] != null ? _audioReviewName(feedback['label']?.toString()) : '짖음 ${feedback['bark_present'] ?? '미확인'}'} · ${feedback['note'] ?? ''}'),
        if (evidence != null) Text('통계 표본: ${evidence['stats']?['sample_count'] ?? 0}개 저장 구간'),
        if (frequency?['status'] == 'ok') ...[
          Text('분당 후보 빈도: 현재 ${(frequency!['current_candidates_per_minute'] as num).toStringAsFixed(1)}회 · 과거 저장 구간 ${(frequency['historical_candidates_per_minute'] as num).toStringAsFixed(1)}회'),
          const Text('구간 길이를 보정한 저장 기록 비교이며 검증된 평소 패턴은 아닙니다.'),
        ],
      ],
    )));
  }

  Widget _mediaCard() {
    final files = (catalog['files'] as List<dynamic>? ?? const []).where((file) => file['type'] == 'audio');
    final audio = mediaResult?['audio'] as Map<String, dynamic>?;
    final video = mediaResult?['video'] as Map<String, dynamic>?;
    return Card(child: Padding(padding: const EdgeInsets.all(20), child: Column(
      crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('공개 영상·음원 입력', style: Theme.of(context).textTheme.titleLarge),
        const Text('서로 다른 공개 자료의 결합은 합성 시연입니다. LSTM 행동 분류의 실제 정확도는 미검증입니다.'),
        if (files.isEmpty) const Text('공개 입력 준비 명령을 먼저 실행해 주세요.'),
        if (files.isNotEmpty) DropdownButton<String>(
          value: audioFilename, isExpanded: true,
          items: files.map((file) => DropdownMenuItem(value: file['filename'].toString(),
            child: Text('${file['category']} · ${file['filename']}'))).toList(),
          onChanged: busy ? null : (value) => setState(() => audioFilename = value),
        ),
        SwitchListTile(contentPadding: EdgeInsets.zero,
          title: const Text('준비된 영상 궤적과 결합'),
          subtitle: Text(catalog['video_prepared'] == true ? '영상 분석 준비됨' : '영상 분석 미준비: 음원만 사용'),
          value: includeVideo && catalog['video_prepared'] == true,
          onChanged: busy || catalog['video_prepared'] != true ? null : (value) => setState(() => includeVideo = value)),
        FilledButton(onPressed: busy || audioFilename == null ? null : analyzePublicMedia,
          child: const Text('공개 입력 분석·케어 제안')),
        if (mediaResult != null) ...[
          const SizedBox(height: 12),
          Text(observation?['context']?['input_note']?.toString() ?? ''),
          if (audio != null) ...[
            Text('음성 이벤트 ${audio['events'].length}개 · ${audio['duration_s']}초'),
            SizedBox(height: 110, width: double.infinity, child: CustomPaint(
              painter: SignalPainter(audio['envelope'] as List<dynamic>, trajectory: false))),
          ],
          if (video != null) ...[
            Image(image: widget.previewProvider ?? NetworkImage('$apiBase/media/preview'), height: 180,
              errorBuilder: (_, error, stack) => const Text('영상 미리보기 로딩 실패')),
            Text('선택 추적 ID ${video['target_track_id']} · 추적 샘플 ${video['tracked_samples']} · 카메라 이동 미보정'),
            if ((video['predictions'] as List<dynamic>).isNotEmpty)
              Text('LSTM 특징 v${video['feature_version'] ?? 1} · 마지막 궤적: ${video['predictions'].last['label']} · 실제 행동 정답 미검증'),
            SizedBox(height: 150, width: 220, child: CustomPaint(
              painter: SignalPainter(video['points'] as List<dynamic>, trajectory: true))),
          ],
          for (final source in mediaResult!['sources']) Padding(padding: const EdgeInsets.only(top: 8),
            child: SelectableText('${source['filename']} · ${source['license']}\n${source['attribution']}\n${source['source_page']}')),
        ],
      ],
    )));
  }

  Widget _timelineCard() {
    return Card(child: Padding(padding: const EdgeInsets.all(20), child: Column(
      crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('전체 처리 타임라인', style: Theme.of(context).textTheme.titleLarge),
        if (timeline.isEmpty) const Text('처리된 이벤트가 없습니다.'),
        for (final event in timeline.take(12)) ListTile(
          contentPadding: EdgeInsets.zero,
          title: Text('${event['type']} #${event['id']} · ${event['detail']}'),
          subtitle: Text(event['at'].toString()),
        ),
      ],
    )));
  }

  Widget _comparisonCard() {
    return Card(child: Padding(padding: const EdgeInsets.all(20), child: Column(
      crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('관찰 비교와 피드백', style: Theme.of(context).textTheme.titleLarge),
        const Text('전후 차이는 음악의 인과 효과가 아닙니다. 평소 패턴은 실제 기록이 충분할 때만 표시합니다.'),
        if (savedFeedback != null) Text('저장한 보호자 의견 #${savedFeedback!['id']} · 관찰 #${savedFeedback!['observation_id']}'),
        TextButton(onPressed: busy || observation == null ? null : loadBaseline,
          child: const Text('동일 시간대의 평소 패턴 조회')),
        if (baseline != null) Text(baseline!['status'] == 'ok'
          ? '표본 ${baseline!['sample_count']}개 · 과거 후보 빈도 ${baseline!['mean_candidate_rate_per_minute']}회/분 · 현재 ${baseline!['current_candidate_rate_per_minute']}회/분'
          : '비교 불가: ${baseline!['reason']}'),
        if (comparison != null) ...[
          Text('명령 ${comparison!['command_id']} · ${comparison!['scope']}'),
          Text(comparison!['status'] == 'ok'
            ? '같은 ${comparison!['window_s']}초 구간: 후보 ${comparison!['before_bark_candidates']} → ${comparison!['after_bark_candidates']}회'
            : '전후 비교 자료 부족: ${comparison!['reason']}'),
        ],
      ],
    )));
  }

  Widget _overview() {
    return LayoutBuilder(builder: (_, constraints) {
      final width = constraints.maxWidth >= 760 ? (constraints.maxWidth - 24) / 3 : constraints.maxWidth;
      return Wrap(
        spacing: 12,
        runSpacing: 12,
        children: [
          _metricCard(width, '최근 관찰', observation == null ? '데이터 없음' : '#${observation!['id']}',
            observation == null ? '외출·음원에서 관찰을 추가해 주세요.' : '출처: ${observation!['source']} · 저장된 최근 기록', Icons.description_outlined),
          _metricCard(
            width,
            '처리 실적',
            '관찰 ${metrics['observations'] ?? 0} · 제안 ${metrics['suggestions'] ?? 0}',
            'MCP ${metrics['mcp_successes'] ?? 0} · Gemini ${metrics['gemini_successes'] ?? 0}',
            Icons.sensors,
          ),
          _metricCard(
            width,
            '음성 신호',
            observation == null ? '데이터 없음' : '음성 분석 기록 확인',
            '외출·음원 화면에서 모델 감지 창과 원본 소리를 확인하세요.',
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
            Icon(icon, size: 30, color: GenesisTheme.secondaryInk),
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
    final careSteps = suggestion!['care_steps'] as List<dynamic>? ?? const [];
    final recommended = suggestion!['recommended_actions'] as List<dynamic>? ?? const [];
    final pending = const {'pending'}
        .contains(suggestion!['status']);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            const Icon(Icons.auto_awesome),
            const SizedBox(width: 8),
            Expanded(child: Text('근거 기반 케어 제안', style: Theme.of(context).textTheme.titleLarge)),
            Chip(label: Text(_severityName(suggestion!['severity']?.toString()))),
          ]),
          const SizedBox(height: 14),
          Text(suggestion!['summary']?.toString() ?? '-', style: Theme.of(context).textTheme.titleMedium),
          if (careSteps.isNotEmpty) ...[
            const SizedBox(height: 16),
            Text('보호자가 해볼 일', style: Theme.of(context).textTheme.labelLarge),
            ...careSteps.map((step) => Padding(
              padding: const EdgeInsets.only(top: 5),
              child: Text('• $step'),
            )),
          ],
          const SizedBox(height: 12),
          Text('판단 근거', style: Theme.of(context).textTheme.labelLarge),
          ...reasons.map((reason) => Padding(
                padding: const EdgeInsets.only(top: 5),
                child: Text('• $reason'),
              )),
          const SizedBox(height: 16),
          Text('제안 상태: ${_statusName(suggestion!['status'])} · 제공자: ${_providerName(suggestion!['provider'])}'),
          Text('제안 #${suggestion!['id']} · 관찰 #${suggestion!['observation_id']}'),
          TextButton(onPressed: busy ? null : recordFeedback, child: const Text('이 제안의 관찰에 보호자 피드백')),
          if (pending && recommended.isNotEmpty) ...[
            const SizedBox(height: 16),
            Wrap(spacing: 8, runSpacing: 8, children: [
              for (final action in recommended)
                FilledButton.icon(
                  onPressed: busy ? null : () => approve(action.toString()),
                  icon: const Icon(Icons.music_note),
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
          for (final item in actions) ...[
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.music_note),
              title: Text(_actionName(item['action_type']?.toString() ?? '')),
              subtitle: Text(item['error']?.toString() ?? item['command_id']?.toString() ?? ''),
              trailing: Chip(label: Text(_statusName(item['status']))),
            ),
            TextButton(onPressed: busy ? null : () => loadComparison(item['command_id'].toString()),
              child: const Text('이 실행의 관찰 전후 비교')),
          ],
        ]),
      ),
    );
  }

  String _actionName(String value) => value == 'music' ? '가상 음악 실행' : value;

  String _audioReviewName(String? value) => const {
    'pet_vocalization': '반려견 소리',
    'external_or_tv': 'TV·외부 소리',
    'other': '기타 소리',
    'uncertain': '판단 어려움',
  }[value] ?? '미확인';

  String _inputModeName(dynamic value) => const {
    'uploaded_audio': '사용자 음원',
    'prepared_video': '준비된 영상·음원',
    'synthetic_demo': '합성 시연',
    'live': '실시간 입력',
  }[value] ?? '알 수 없는 입력';

  String _providerName(dynamic value) {
    final name = value?.toString() ?? '';
    if (name.startsWith('gemini:')) return 'Gemini AI';
    if (name == 'rule-fallback') return '기본 판단(대체 동작)';
    if (name == 'rule') return '기본 케어 판단';
    return name;
  }

  String _severityName(String? value) => const {
        'info': '정보',
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
        'timed_out': '응답 시간초과',
        'action_failed': '실행 실패',
      }[value] ?? value?.toString() ?? '-';
}

class SignalPainter extends CustomPainter {
  SignalPainter(this.data, {required this.trajectory});
  final List<dynamic> data;
  final bool trajectory;

  @override
  void paint(Canvas canvas, Size size) {
    canvas.drawRect(Offset.zero & size, Paint()..color = GenesisTheme.background);
    if (data.length < 2) return;
    final maxTime = (data.last['t'] as num).toDouble();
    final maxRms = trajectory ? 1.0 : data.map((point) => (point['rms'] as num).toDouble()).fold<double>(.00001, (a, b) => a > b ? a : b);
    final path = Path();
    for (var i = 0; i < data.length; i++) {
      final point = data[i];
      final x = trajectory ? (point['cx'] as num).toDouble() : (point['t'] as num).toDouble() / (maxTime == 0 ? 1 : maxTime);
      final y = trajectory ? (point['cy'] as num).toDouble() : 1 - (point['rms'] as num).toDouble() / maxRms;
      if (i == 0 || (trajectory && (point['t'] as num) - (data[i-1]['t'] as num) > .5)) {
        path.moveTo(x * size.width, y * size.height);
      } else {
        path.lineTo(x * size.width, y * size.height);
      }
    }
    canvas.drawPath(path, Paint()..color = GenesisTheme.secondaryInk..style = PaintingStyle.stroke..strokeWidth = 2);
  }

  @override
  bool shouldRepaint(covariant SignalPainter oldDelegate) => data != oldDelegate.data || trajectory != oldDelegate.trajectory;
}

class ProfileEditor extends StatefulWidget {
  const ProfileEditor({super.key, this.profile});
  final Map<String, dynamic>? profile;
  @override
  State<ProfileEditor> createState() => _ProfileEditorState();
}

class FeedbackEditor extends StatefulWidget {
  const FeedbackEditor({super.key});
  @override
  State<FeedbackEditor> createState() => _FeedbackEditorState();
}

class _FeedbackEditorState extends State<FeedbackEditor> {
  bool? bark;
  bool? appropriate;
  final note = TextEditingController();
  @override
  void dispose() { note.dispose(); super.dispose(); }
  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('보호자 피드백'),
    content: SizedBox(width: 460, child: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
      const Text('해당 관찰의 실제 짖음 여부'),
      DropdownButton<bool>(value: bark, hint: const Text('미확인'), isExpanded: true,
        items: const [DropdownMenuItem(value: true, child: Text('짖음이 있었음')), DropdownMenuItem(value: false, child: Text('짖음이 아니었음'))],
        onChanged: (value) => setState(() => bark = value)),
      const Text('제안 적절성'),
      DropdownButton<bool>(value: appropriate, hint: const Text('미확인'), isExpanded: true,
        items: const [DropdownMenuItem(value: true, child: Text('적절했음')), DropdownMenuItem(value: false, child: Text('적절하지 않았음'))],
        onChanged: (value) => setState(() => appropriate = value)),
      TextField(controller: note, maxLength: 1000, maxLines: 3,
        decoration: const InputDecoration(labelText: '검토 의견'), onChanged: (_) => setState(() {})),
      const Text('보호자 의견으로 보관하며 자동 학습 정답으로 간주하지 않습니다.'),
    ]))),
    actions: [
      TextButton(onPressed: () => Navigator.pop(context), child: const Text('취소')),
      FilledButton(onPressed: bark == null && appropriate == null && note.text.trim().isEmpty ? null : () {
        Navigator.pop(context, {'bark_present': bark, 'suggestion_appropriate': appropriate, 'note': note.text});
      }, child: const Text('피드백 저장')),
    ],
  );
}

class _ProfileEditorState extends State<ProfileEditor> {
  final form = GlobalKey<FormState>();
  late final TextEditingController name;
  late final TextEditingController age;
  late final TextEditingController pattern;
  late final TextEditingController note;
  @override
  void initState() {
    super.initState();
    name = TextEditingController(text: widget.profile?['name']?.toString() ?? '');
    age = TextEditingController(text: widget.profile?['age_years']?.toString() ?? '');
    pattern = TextEditingController(text: widget.profile?['living_pattern']?.toString() ?? '');
    note = TextEditingController(text: widget.profile?['guardian_note']?.toString() ?? '');
  }
  @override
  void dispose() {
    name.dispose(); age.dispose(); pattern.dispose(); note.dispose();
    super.dispose();
  }
  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('반려견 프로필 · 보호자 입력'),
    content: SizedBox(width: 460, child: Form(key: form, child: SingleChildScrollView(child: Column(
      mainAxisSize: MainAxisSize.min, children: [
        TextFormField(controller: name, maxLength: 80, decoration: const InputDecoration(labelText: '이름'),
          validator: (value) => value == null || value.trim().isEmpty ? '이름을 입력해 주세요.' : null),
        TextFormField(controller: age, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: '나이 (선택)'),
          validator: (value) {
            if (value == null || value.isEmpty) return null;
            final parsed = double.tryParse(value);
            return parsed == null || !parsed.isFinite || parsed < 0 || parsed > 35 ? '0~35 사이 숫자를 입력해 주세요.' : null;
          }),
        TextFormField(controller: pattern, maxLength: 500, decoration: const InputDecoration(labelText: '생활 패턴 (선택)')),
        TextFormField(controller: note, maxLength: 1000, maxLines: 3, decoration: const InputDecoration(labelText: '관찰 특이사항·메모 (선택)')),
        const Text('이 정보는 보호자 입력이며 실제 측정값과 구분하여 다음 제안의 참고 자료로 사용합니다.'),
      ],
    )))),
    actions: [
      TextButton(onPressed: () => Navigator.pop(context), child: const Text('취소')),
      FilledButton(onPressed: () {
        if (!form.currentState!.validate()) return;
        Navigator.pop(context, {'name': name.text.trim(), 'age_years': age.text.isEmpty ? null : double.parse(age.text),
          'living_pattern': pattern.text, 'guardian_note': note.text});
      }, child: const Text('저장')),
    ],
  );
}
