import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'audio_input.dart';
import 'clip_view.dart';
import 'genesis_theme.dart';

typedef AudioInputBuilder = Widget Function(
  void Function(String, Uint8List) onSelected,
  void Function(String) onError,
);

class AudioPanel extends StatefulWidget {
  const AudioPanel({super.key, required this.client, required this.base, required this.petId,
    required this.onChanged, this.outing, this.inputBuilder, this.allowUpload = true});
  final bool allowUpload;
  final http.Client client;
  final String base, petId;
  final Map<String, dynamic>? outing;
  final VoidCallback onChanged;
  final AudioInputBuilder? inputBuilder;
  @override
  State<AudioPanel> createState() => _AudioPanelState();
}

class _AudioPanelState extends State<AudioPanel> {
  List<dynamic> clips = [];
  List<dynamic> reviewQueue = [];
  bool queueOnly = false;
  Uint8List? bytes;
  String filename = '', error = '';
  bool store = false, training = false, busy = false;
  bool publicDemo = false;
  String publicSource = '';
  int retention = 7, epoch = 0, uploadRevision = 0;
  String get petQuery => 'pet_id=${Uri.encodeQueryComponent(widget.petId)}';
  String scoreLabel(dynamic value) => value is num
    ? '${(value * 100).toStringAsFixed(1)} / 100' : '값 없음';
  String reviewLabel(dynamic value) => const {
    'pet_vocalization': '반려견 소리',
    'external_or_tv': 'TV·외부 소리',
    'other': '기타 소리',
    'uncertain': '판단하기 어려움',
  }[value] ?? '판정 없음';
  String expiryLabel(dynamic value) {
    final time = DateTime.tryParse(value?.toString() ?? '')?.toUtc()
      .add(const Duration(hours: 9));
    if (time == null) return '정보 없음';
    return '${time.year}년 ${time.month}월 ${time.day}일 '
      '${time.hour.toString().padLeft(2, '0')}:${time.minute.toString().padLeft(2, '0')} (한국 시간)';
  }
  @override
  void initState() { super.initState(); load(); }
  @override
  void didUpdateWidget(covariant AudioPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.petId != widget.petId) {
      epoch++; uploadRevision++; clips = []; reviewQueue = []; queueOnly = false; bytes = null; filename = ''; store = false; training = false; error = ''; publicDemo = false; publicSource = ''; retention = 7;
      load();
    }
  }
  dynamic decode(http.Response response) {
    dynamic data;
    try { data = jsonDecode(utf8.decode(response.bodyBytes)); }
    catch (_) {
      if (response.statusCode >= 400) {
        throw Exception('서버 응답 오류 (HTTP ${response.statusCode}). 다시 시도해 주세요.');
      }
      throw const FormatException('서버 응답 형식이 올바르지 않습니다.');
    }
    if (response.statusCode >= 400) {
      throw Exception(data is Map && data['detail'] != null
        ? data['detail'] : '서버 응답 오류 (HTTP ${response.statusCode}). 다시 시도해 주세요.');
    }
    return data;
  }
  Future<void> load() async {
    final token = ++epoch;
    try {
      final data = decode(await widget.client.get(Uri.parse('${widget.base}/audio-clips?$petQuery')).timeout(const Duration(seconds: 20)));
      if (!mounted || token != epoch) { return; }
      dynamic queue;
      var queueUnavailable = false;
      try {
        queue = decode(await widget.client.get(Uri.parse('${widget.base}/audio-clips/review-queue?$petQuery'))
          .timeout(const Duration(seconds: 20)));
      } catch (_) { queueUnavailable = true; }
      if (mounted && token == epoch) {
        setState(() {
          clips = data as List<dynamic>;
          reviewQueue = queue is Map ? queue['items'] as List<dynamic> : [];
          if (queueUnavailable) queueOnly = false;
          error = queueUnavailable ? '확인 추천을 불러오지 못했습니다. 전체 음원 목록은 표시 중입니다.' : '';
        });
      }
    } catch (e) { if (mounted && token == epoch) setState(() => error = '$e'); }
  }
  Future<void> run(Future<void> Function() action) async {
    if (busy) return;
    final pet = widget.petId;
    setState(() { busy = true; error = ''; });
    try { await action(); if (mounted && pet == widget.petId) { await load(); widget.onChanged(); } }
    catch (e) { if (mounted && pet == widget.petId) setState(() => error = '$e'); }
    finally { if (mounted) setState(() => busy = false); }
  }
  Future<void> post(String path, Map<String, dynamic> body) async {
    decode(await widget.client.post(Uri.parse('${widget.base}$path'),
      headers: {'Content-Type':'application/json'}, body: jsonEncode(body)).timeout(const Duration(seconds: 30)));
  }
  Future<void> upload() async {
    if (bytes == null || !store) return;
    final pet = widget.petId;
    final allowed = widget.outing == null || widget.outing!['input_mode'] == 'uploaded_audio';
    if (!allowed) { setState(() => error = '기존 외출을 종료하고 사용자 음원 모드로 시작해 주세요.'); return; }
    if (publicDemo && publicSource.trim().length < 5) {
      setState(() => error = '시연 음원 설명을 5자 이상 적어 주세요.'); return;
    }
    final query = '$petQuery&store_consent=$store&training_consent=$training&retention_days=$retention'
      '${widget.outing == null ? '' : '&outing_id=${widget.outing!['id']}'}'
      '${publicDemo ? '&demo_source=${Uri.encodeQueryComponent(publicSource.trim())}' : ''}';
    final content = bytes!;
    await run(() async {
      decode(await widget.client.post(Uri.parse('${widget.base}/audio-clips/upload?$query'),
        headers: {'Content-Type':'audio/wav'}, body: content).timeout(const Duration(seconds: 60)));
      if (mounted && pet == widget.petId) {
        setState(() {
          bytes = null; filename = ''; publicDemo = false; publicSource = '';
          store = false; training = false; retention = 7; uploadRevision++;
        });
      }
    });
  }
  Future<void> review(Map<String, dynamic> item) async {
    final pet = widget.petId;
    String label = item['review']?['label'] ?? 'uncertain';
    String note = item['review']?['note'] ?? '';
    final result = await showDialog<Map<String,dynamic>>(context: context, builder: (context) =>
      StatefulBuilder(builder: (context, update) => AlertDialog(title: const Text('소리 확인 의견'),
        content: SizedBox(width: 450, child: Column(mainAxisSize: MainAxisSize.min, children: [
          DropdownButton<String>(value: label, isExpanded: true, items: const [
            DropdownMenuItem(value:'pet_vocalization',child:Text('반려견 소리')),
            DropdownMenuItem(value:'external_or_tv',child:Text('TV·외부 소리')),
            DropdownMenuItem(value:'other',child:Text('기타 소리')),
            DropdownMenuItem(value:'uncertain',child:Text('판단하기 어려움')),
          ],onChanged:(value) => update(() => label = value!)),
          TextFormField(initialValue:note,onChanged:(value) => note = value,maxLength:1000,decoration:const InputDecoration(labelText:'상황 메모')),
          Text(item['analysis']?['demo_source'] == null
            ? '보호자 의견으로 저장됩니다. 모델의 확정 정답이나 감정 진단이 아닙니다.'
            : '공개 자료 시연 담당자 의견으로 저장됩니다. 실제 보호자 확인이나 모델 정답이 아닙니다.'),
        ])), actions: [TextButton(onPressed:() => Navigator.pop(context),child:const Text('취소')),
          FilledButton(onPressed:() => Navigator.pop(context,{'pet_id':pet,'label':label,'note':note}),child:const Text('의견 저장'))])));
    if (result != null && mounted && pet == widget.petId) await run(() => post('/audio-clips/${item['id']}/review',result));
  }
  void play(Map<String,dynamic> item, [double? start, double? end]) {
    final segment = start == null || end == null ? '' : '&start_s=$start&end_s=$end';
    showDialog<void>(context:context,builder:(context) => AlertDialog(title:const Text('원본 음원 확인'),
      content:SizedBox(width:650,height:300,child:clipView('${widget.base}/audio-clips/${item['id']}/player?$petQuery$segment')),
      actions:[TextButton(onPressed:() => Navigator.pop(context),child:const Text('닫기'))]));
  }
  @override
  Widget build(BuildContext context) => ExpansionTile(
    tilePadding: const EdgeInsets.symmetric(horizontal: 8),
    childrenPadding: const EdgeInsets.only(bottom: 8),
    title: Text(widget.allowUpload ? '사용자 음원 · 보호자 확인' : '자동 수집 음원 · 보호자 확인', style: Theme.of(context).textTheme.titleMedium),
    subtitle: Text(widget.allowUpload ? '30초 이하 WAV · 모델 학습 참여는 별도 선택' : '수집한 소리를 확인하고 의견을 남기세요.',
      style: Theme.of(context).textTheme.bodySmall),children:[
    Padding(padding:const EdgeInsets.all(12),child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
      if (widget.allowUpload) ...[
      KeyedSubtree(key: ValueKey(uploadRevision), child: (widget.inputBuilder ?? audioInput)(
        (name,data) { if (mounted) setState(() { filename = name; bytes = data; }); },
        (message) { if (mounted) setState(() => error = message); })),
      if (filename.isNotEmpty) Text('선택: $filename'),
      CheckboxListTile(value: publicDemo, onChanged: busy ? null : (v) => setState(() {
        publicDemo = v!; publicSource = ''; if (publicDemo) training = false;
      }),
        title: const Text('공개·생성 자료 시연용 음원')),
      if (publicDemo) TextField(onChanged: (v) => publicSource = v,
        decoration: const InputDecoration(labelText: '시연 음원 설명', hintText: '예: 초인종과 노크 뒤 개가 짖는 소리가 들립니다')),
      if (publicDemo) const Text('시연 자료이며 실제 반려견의 장기 관찰이나 모델 학습 정답으로 사용하지 않습니다.'),
      CheckboxListTile(value:store,onChanged:busy ? null : (v) => setState(() { store = v!; if (!store) training = false; }),
        title:Text(publicDemo ? '시연용 기록으로 음원 저장에 동의' : '개인 관찰 기록으로 음원 저장에 동의')),
      CheckboxListTile(value:training,onChanged:busy || !store || publicDemo ? null : (v) => setState(() => training = v!),
        title:const Text('검수 후 공통 모델 개선에 제공 (선택)')),
      DropdownButton<int>(value:retention,items:[1,7,30].map((n) => DropdownMenuItem(value:n,child:Text('원본 보관 $n일'))).toList(),
        onChanged:busy ? null : (v) => setState(() => retention = v!)),
      const Text('원본 삭제 후에도 관찰 수치와 확인 의견은 남습니다. 현재는 로컬 단일 사용자용입니다.'),
      FilledButton(onPressed:busy || bytes == null || !store ? null : upload,child:const Text('음원 업로드·분석')),
      ],
      TextButton(onPressed:busy ? null : load,child:const Text('음원 목록 새로고침')),
      TextButton(onPressed:busy ? null : () => setState(() => queueOnly = !queueOnly),
        child:Text(queueOnly ? '전체 음원 보기' : '확인 추천 ${reviewQueue.length}건 보기')),
      if (queueOnly) const Text('판별이 애매한 구간과 일반 구간 표본을 함께 확인합니다. 업로드하지 않은 소리의 누락은 측정할 수 없습니다.'),
      if (queueOnly && reviewQueue.isEmpty) const Text('확인이 필요한 새 음원이 없습니다.'),
      if (clips.isEmpty) const Text('아직 저장된 사용자 음원이 없습니다.'),
      for (final raw in queueOnly ? reviewQueue : clips) Builder(builder:(context) {
        final item = Map<String,dynamic>.from(raw);
        final model = item['analysis']?['audio_model'] ?? item['analysis']?['audio_lstm'];
        final modelName = model?['model_name'] ?? 'LSTM';
        return Padding(padding: const EdgeInsets.only(bottom: 12), child: Card(child:Padding(
          padding:const EdgeInsets.all(16),child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
          Text('관찰 #${item['observation_id']} · ${item['duration_s']}초',
            style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          Text(item['source_note'] ?? '출처 정보 없음', style: Theme.of(context).textTheme.bodySmall),
          const SizedBox(height: 8),
          Chip(
            backgroundColor: item['review_priority'] == 'routine_sample'
              ? const Color(0xFFF4F4F5) : const Color(0xFFFFF7E6),
            label: Text(item['review_priority'] == 'uncertain' ? '확인 권장: 모델 점수가 기준에 가깝습니다.' : '일반 구간 확인 표본',
              style: TextStyle(color: item['review_priority'] == 'routine_sample'
              ? GenesisTheme.secondaryInk : GenesisTheme.warningInk))),
          if (model?['model_role'] == 'experimental')
            Text('$modelName 비교 시험 · 실제 가정 성능 미검증 · 공개 시연 자료는 별도 표시'),
          if (model != null) Text('$modelName 개 짖음 소리 후보 점수 ${scoreLabel(model['dog_score'])} · 기준 ${scoreLabel(model['threshold'])} (정확도·확률 아님)',
            style: Theme.of(context).textTheme.bodySmall),
          if (model?['windows'] is List && (model['windows'] as List).isNotEmpty) ...[
            const SizedBox(height: 12),
            Text('음원 분석 구간 · 5초 창은 정확한 발성 시작·종료 시각이 아닙니다.',
              style: Theme.of(context).textTheme.bodySmall),
            for (final rawWindow in model['windows']) Builder(builder: (context) {
              final window = Map<String,dynamic>.from(rawWindow);
              final start = (window['start_s'] as num).toDouble();
              final end = (window['end_s'] as num).toDouble();
              return ListTile(
                dense: true,
                title: Text('${start.toStringAsFixed(1)}~${end.toStringAsFixed(1)}초 · ${window['label'] == 'dog_candidate' ? '개 짖음 소리 후보' : '기타 소리 후보'}'),
                subtitle: Text('모델 점수 ${((window['dog_score'] as num) * 100).toStringAsFixed(1)} / 100 · '
                  '${item['analysis']?['demo_source'] == null ? '보호자' : '시연 담당자'} 확인 ${item['review']?['label'] == null ? '전' : '의견 있음'}'),
                trailing: TextButton(onPressed: item['audio_available'] == true ? () => play(item, start, end) : null,
                  child: const Text('구간 듣기')),
              );
            }),
          ],
          if (model == null) const Text('음성 모델이 준비되지 않았거나 분석에 실패했습니다. 소리 크기 변화만으로 짖음을 판별할 수 없습니다.'),
          if ((item['review'] as Map).isNotEmpty) Text('${item['review']['source'] == 'demo_operator_opinion' ? '시연 담당자 의견' : '보호자 의견'}: ${reviewLabel(item['review']['label'])} · ${item['review']['note']}'),
          Text('학습 참여 ${item['training_consent'] == true ? '동의' : '미동의'} · 원본 만료 ${expiryLabel(item['expires_at'])}'),
          Wrap(spacing:8,children:[
            TextButton(onPressed:item['audio_available'] == true ? () => play(item) : null,child:Text(item['deleted'] == true ? '원본 삭제됨' : '음원 듣기')),
            TextButton(onPressed:busy ? null : () => review(item),child:const Text('확인 의견')),
            if (item['training_consent'] == true) TextButton(onPressed:busy ? null : () => run(() => post('/audio-clips/${item['id']}/consent',
              {'pet_id':widget.petId,'training_consent':false})),child:const Text('학습 참여 철회')),
            if (item['deleted'] != true) TextButton(onPressed:busy ? null : () async {
              final pet = widget.petId;
              final yes = await showDialog<bool>(context:context,builder:(context) => AlertDialog(title:const Text('원본 음원을 삭제할까요?'),
                content:const Text('복구할 수 없습니다. 학습 참여도 철회됩니다. 관찰 수치와 의견은 남습니다.'),
                actions:[TextButton(onPressed:() => Navigator.pop(context,false),child:const Text('취소')),
                  FilledButton(onPressed:() => Navigator.pop(context,true),child:const Text('원본 삭제'))]));
              if (yes == true && mounted && pet == widget.petId) await run(() => post('/audio-clips/${item['id']}/delete-original?$petQuery',{}));
            },child:const Text('원본 삭제')),
          ]),
        ]))));
      }),
      if (busy) const LinearProgressIndicator(),
      if (error.isNotEmpty) Text(error,style:const TextStyle(color: GenesisTheme.warningInk)),
    ])),
  ]);
}
