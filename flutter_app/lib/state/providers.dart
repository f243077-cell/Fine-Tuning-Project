import 'dart:async';
import 'dart:convert';

import 'package:flutter/services.dart' show rootBundle;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;

import '../api/clients.dart';
import '../api/models.dart';
import '../config.dart';

// --- services -------------------------------------------------------------------------------------------------
final configProvider = Provider<AppConfig>((ref) => AppConfig.fromEnvironment());

final httpClientProvider = Provider<http.Client>((ref) {
  final client = http.Client();
  ref.onDispose(client.close);
  return client;
});

final guardApiProvider = Provider<GuardApi>((ref) {
  final cfg = ref.watch(configProvider);
  return GuardApi(cfg.guardUrl, cfg.guardApiKey, ref.watch(httpClientProvider));
});

final demoApiProvider = Provider<DemoApi>((ref) => DemoApi(ref.watch(configProvider).demoUrl, ref.watch(httpClientProvider)));

final healthProvider = FutureProvider<Health>((ref) => ref.watch(guardApiProvider).health());

// --- navigation ---------------------------------------------------------------------------------------------------
enum AppTab {
  scan('Scan'),
  compare('Compare'),
  chat('Chat'),
  library('Attack library'),
  history('History');

  const AppTab(this.label);
  final String label;
}

class TabNotifier extends Notifier<AppTab> {
  @override
  AppTab build() => AppTab.scan;

  void go(AppTab tab) => state = tab;
}

final tabProvider = NotifierProvider<TabNotifier, AppTab>(TabNotifier.new);

// --- sample library -------------------------------------------------------------------------------------------------
class Sample {
  const Sample({required this.id, required this.title, required this.lang, required this.kind, required this.source, required this.text});

  factory Sample.fromJson(Map<String, dynamic> j) => Sample(
        id: j['id'] as String,
        title: j['title'] as String,
        lang: j['lang'] as String,
        kind: j['kind'] as String,
        source: Source.values.firstWhere((s) => s.wire == j['source']),
        text: j['text'] as String,
      );

  final String id;
  final String title;
  final String lang; // en | ru_mix | ru_pure
  final String kind; // attack type or "benign"
  final Source source;
  final String text;

  bool get isAttack => kind != 'benign';
}

final samplesProvider = FutureProvider<List<Sample>>((ref) async {
  final raw = jsonDecode(await rootBundle.loadString('assets/samples.json')) as Map<String, dynamic>;
  return [for (final s in raw['samples'] as List) Sample.fromJson(s as Map<String, dynamic>)];
});

// --- history (memory only) -------------------------------------------------------------------------------------------
class HistoryEntry {
  const HistoryEntry({required this.at, required this.text, required this.source, required this.result});
  final DateTime at;
  final String text;
  final Source source;
  final ScanResult result;
}

class HistoryNotifier extends Notifier<List<HistoryEntry>> {
  @override
  List<HistoryEntry> build() => const [];

  void add(HistoryEntry e) => state = [e, ...state];

  void clear() => state = const [];
}

final historyProvider = NotifierProvider<HistoryNotifier, List<HistoryEntry>>(HistoryNotifier.new);

// --- scan ---------------------------------------------------------------------------------------------------------------
class ScanState {
  const ScanState({this.text = '', this.source = Source.userInput, this.loading = false, this.result, this.scannedText, this.scannedSource, this.error, this.revision = 0});

  final String text;
  final Source source;
  final bool loading;
  final ScanResult? result;
  final String? scannedText;
  final Source? scannedSource;
  final String? error;
  final int revision; // bumps when the text is replaced from outside the text field

  ScanState copyWith({String? text, Source? source, bool? loading, ScanResult? result, String? scannedText, Source? scannedSource, String? error, bool clearError = false, int? revision}) =>
      ScanState(
        text: text ?? this.text,
        source: source ?? this.source,
        loading: loading ?? this.loading,
        result: result ?? this.result,
        scannedText: scannedText ?? this.scannedText,
        scannedSource: scannedSource ?? this.scannedSource,
        error: clearError ? null : (error ?? this.error),
        revision: revision ?? this.revision,
      );
}

class ScanController extends Notifier<ScanState> {
  @override
  ScanState build() => const ScanState();

  void setText(String text) => state = state.copyWith(text: text);

  void setSource(Source source) => state = state.copyWith(source: source);

  void loadSample(Sample s) =>
      state = state.copyWith(text: s.text, source: s.source, clearError: true, revision: state.revision + 1);

  Future<void> scan() async {
    final text = state.text.trim();
    if (text.isEmpty || state.loading) return;
    state = state.copyWith(loading: true, clearError: true);
    try {
      final result = await ref.read(guardApiProvider).scan(text, state.source);
      state = state.copyWith(loading: false, result: result, scannedText: text, scannedSource: state.source);
      ref.read(historyProvider.notifier).add(HistoryEntry(at: DateTime.now(), text: text, source: state.source, result: result));
    } on ApiException catch (e) {
      state = state.copyWith(loading: false, error: e.message);
    }
  }
}

final scanProvider = NotifierProvider<ScanController, ScanState>(ScanController.new);

// --- compare guard off vs on ----------------------------------------------------------------------------------------------
class CompareSide {
  const CompareSide({this.loading = false, this.answer, this.error});
  final bool loading;
  final ChatAnswer? answer;
  final String? error;
}

class CompareState {
  const CompareState({this.question = '', this.off = const CompareSide(), this.on = const CompareSide(), this.revision = 0});
  final String question;
  final CompareSide off;
  final CompareSide on;
  final int revision;

  bool get running => off.loading || on.loading;
}

class CompareController extends Notifier<CompareState> {
  @override
  CompareState build() => const CompareState();

  void setQuestion(String q) => state = CompareState(question: q, off: state.off, on: state.on, revision: state.revision);

  void loadSample(Sample s) => state = CompareState(question: s.text, revision: state.revision + 1);

  Future<CompareSide> _side(String q, bool guard) async {
    try {
      return CompareSide(answer: await ref.read(demoApiProvider).chat(q, guard: guard));
    } on ApiException catch (e) {
      return CompareSide(error: e.message);
    }
  }

  /// Runs guard off first, then guard on (one at a time, so the CPU chat model is not shared).
  Future<void> run() async {
    final q = state.question.trim();
    if (q.isEmpty || state.running) return;
    state = CompareState(question: q, off: const CompareSide(loading: true), on: const CompareSide(loading: true), revision: state.revision);
    final off = await _side(q, false);
    state = CompareState(question: q, off: off, on: const CompareSide(loading: true), revision: state.revision);
    final on = await _side(q, true);
    state = CompareState(question: q, off: off, on: on, revision: state.revision);
  }
}

final compareProvider = NotifierProvider<CompareController, CompareState>(CompareController.new);

// --- streaming chat -----------------------------------------------------------------------------------------------------------
class ChatTurn {
  const ChatTurn({required this.question, this.steps = const [], this.answer, this.error, this.streaming = true, this.stopped = false});
  final String question;
  final List<StepEvent> steps;
  final ChatAnswer? answer;
  final String? error;
  final bool streaming;
  final bool stopped;

  ChatTurn copyWith({List<StepEvent>? steps, ChatAnswer? answer, String? error, bool? streaming, bool? stopped}) => ChatTurn(
        question: question,
        steps: steps ?? this.steps,
        answer: answer ?? this.answer,
        error: error ?? this.error,
        streaming: streaming ?? this.streaming,
        stopped: stopped ?? this.stopped,
      );
}

class ChatController extends Notifier<List<ChatTurn>> {
  Completer<void>? _stop;

  @override
  List<ChatTurn> build() => const [];

  bool get busy => state.isNotEmpty && state.last.streaming;

  void _updateLast(ChatTurn Function(ChatTurn) f) => state = [...state.sublist(0, state.length - 1), f(state.last)];

  Future<void> send(String question) async {
    final q = question.trim();
    if (q.isEmpty || busy) return;
    final stop = _stop = Completer<void>();
    state = [...state, ChatTurn(question: q)];
    try {
      await for (final ev in ref.read(demoApiProvider).stream(q, stop.future)) {
        switch (ev) {
          case StepEvent():
            _updateLast((t) => t.copyWith(steps: [...t.steps, ev]));
          case FinalEvent():
            _updateLast((t) => t.copyWith(answer: ev.answer));
        }
      }
      _updateLast((t) => t.copyWith(streaming: false, stopped: stop.isCompleted && t.answer == null));
    } on ApiException catch (e) {
      _updateLast((t) => t.copyWith(error: e.message, streaming: false));
    } catch (e) {
      _updateLast((t) => t.copyWith(error: 'The stream broke off: $e', streaming: false));
    }
  }

  void stop() {
    if (_stop != null && !_stop!.isCompleted) _stop!.complete();
    if (busy) _updateLast((t) => t.copyWith(streaming: false, stopped: true));
  }

  void clear() {
    stop();
    state = const [];
  }
}

final chatProvider = NotifierProvider<ChatController, List<ChatTurn>>(ChatController.new);
