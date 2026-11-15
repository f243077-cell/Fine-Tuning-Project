/// Data classes for the guard-api and demo-rag HTTP contracts (Architecture.md sections 7 and 12).
library;

enum Source {
  userInput('user_input', 'User input'),
  retrievedChunk('retrieved_chunk', 'Retrieved document'),
  toolOutput('tool_output', 'Tool output');

  const Source(this.wire, this.label);
  final String wire;
  final String label;
}

class ScanResult {
  const ScanResult({
    required this.requestId,
    required this.verdict,
    required this.attackType,
    required this.action,
    required this.model,
    required this.latencyMs,
    required this.windows,
    required this.scannerError,
  });

  factory ScanResult.fromJson(Map<String, dynamic> j) => ScanResult(
        requestId: j['request_id'] as String,
        verdict: j['verdict'] as String,
        attackType: j['attack_type'] as String?,
        action: j['action'] as String,
        model: j['model'] as String,
        latencyMs: (j['latency_ms'] as num).toInt(),
        windows: (j['windows'] as num).toInt(),
        scannerError: j['scanner_error'] as String?,
      );

  final String requestId;
  final String verdict; // safe | injection | error
  final String? attackType;
  final String action; // allow | block | drop_chunk | redact_tool_output | log_only
  final String model;
  final int latencyMs;
  final int windows;
  final String? scannerError;

  bool get isInjection => verdict == 'injection';
  bool get isError => verdict == 'error';
}

class GuardEvent {
  const GuardEvent({required this.checkpoint, required this.action, this.id, this.verdict, this.attackType, this.reason});

  factory GuardEvent.fromJson(Map<String, dynamic> j) => GuardEvent(
        checkpoint: j['checkpoint'] as String,
        action: j['action'] as String,
        id: j['id'] as String?,
        verdict: j['verdict'] as String?,
        attackType: j['attack_type'] as String?,
        reason: j['scanner_error'] as String?,
      );

  final String checkpoint; // G1, G2, G4
  final String action;
  final String? id;
  final String? verdict;
  final String? attackType;
  final String? reason;

  bool get stopped => action != 'allow' && action != 'log_only';
}

class Citation {
  const Citation(this.docId, this.title);
  final String docId;
  final String title;
}

class ChatAnswer {
  const ChatAnswer({
    required this.answer,
    required this.sources,
    required this.blocked,
    required this.refused,
    required this.guard,
    required this.events,
  });

  factory ChatAnswer.fromJson(Map<String, dynamic> j) => ChatAnswer(
        answer: j['answer'] as String,
        sources: [
          for (final s in (j['sources'] as List? ?? const []))
            Citation((s as Map)['doc_id'] as String, s['title'] as String),
        ],
        blocked: j['blocked'] as bool? ?? false,
        refused: j['refused'] as String?,
        guard: j['guard'] as bool? ?? true,
        events: [for (final e in (j['guard_events'] as List? ?? const [])) GuardEvent.fromJson(e as Map<String, dynamic>)],
      );

  final String answer;
  final List<Citation> sources;
  final bool blocked;
  final String? refused;
  final bool guard;
  final List<GuardEvent> events;
}

/// One server-sent event from GET /chat/stream: a graph step, or the final answer.
sealed class StreamEvent {
  const StreamEvent();
}

class StepEvent extends StreamEvent {
  const StepEvent(this.node, this.events);
  final String node;
  final List<GuardEvent> events;
}

class FinalEvent extends StreamEvent {
  const FinalEvent(this.answer);
  final ChatAnswer answer;
}

class Health {
  const Health({required this.ok, required this.model});
  final bool ok;
  final String model;
}

class ApiException implements Exception {
  const ApiException(this.message, [this.status]);
  final String message;
  final int? status;

  @override
  String toString() => message;
}
