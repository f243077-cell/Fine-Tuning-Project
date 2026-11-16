import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'models.dart';

const _timeout = Duration(seconds: 120);

String _detail(http.Response r) {
  try {
    final body = jsonDecode(r.body);
    if (body is Map && body['detail'] != null) return body['detail'].toString();
  } catch (_) {
    // not JSON
  }
  return r.reasonPhrase ?? 'HTTP ${r.statusCode}';
}

ApiException _error(http.Response r) => switch (r.statusCode) {
      401 => const ApiException('The guard rejected the API key. Start the app with --dart-define=GUARD_API_KEY=...', 401),
      403 => const ApiException('demo-rag does not allow the guard override. Start it with ALLOW_GUARD_TOGGLE=true.', 403),
      413 => const ApiException('The text is too long (12,000 characters at most). Split it and scan each part.', 413),
      429 => const ApiException('Too many requests in a minute. Wait a moment and try again.', 429),
      _ => ApiException('${r.statusCode}: ${_detail(r)}', r.statusCode),
    };

/// guard-api client: POST /v1/scan and GET /health.
class GuardApi {
  GuardApi(this.baseUrl, this.apiKey, this._http);

  final String baseUrl;
  final String apiKey;
  final http.Client _http;

  Future<ScanResult> scan(String text, Source source) async {
    final http.Response r;
    try {
      r = await _http
          .post(Uri.parse('$baseUrl/v1/scan'),
              headers: {'Content-Type': 'application/json', if (apiKey.isNotEmpty) 'X-API-Key': apiKey},
              body: jsonEncode({'text': text, 'source': source.wire}))
          .timeout(_timeout);
    } on TimeoutException {
      throw const ApiException('The guard did not answer in time.');
    } on http.ClientException {
      throw ApiException('Cannot reach the guard at $baseUrl. Is guard-api running?');
    }
    // A 503 still carries a full result: verdict "error" and the fail-mode action.
    if (r.statusCode == 200 || (r.statusCode == 503 && r.body.contains('"verdict"'))) {
      return ScanResult.fromJson(jsonDecode(r.body) as Map<String, dynamic>);
    }
    throw _error(r);
  }

  Future<Health> health() async {
    try {
      final r = await _http.get(Uri.parse('$baseUrl/health')).timeout(const Duration(seconds: 6));
      final j = jsonDecode(r.body) as Map<String, dynamic>;
      return Health(ok: j['status'] == 'ok', model: j['model'] as String? ?? '?');
    } catch (_) {
      return const Health(ok: false, model: 'offline');
    }
  }
}

/// demo-rag client: POST /chat (with an optional guard override) and GET /chat/stream (SSE).
class DemoApi {
  DemoApi(this.baseUrl, this._http);

  final String baseUrl;
  final http.Client _http;

  Future<ChatAnswer> chat(String question, {bool? guard}) async {
    final http.Response r;
    try {
      r = await _http
          .post(Uri.parse('$baseUrl/chat'),
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode({'question': question, if (guard != null) 'guard': guard ? 'on' : 'off'}))
          .timeout(const Duration(seconds: 600));
    } on TimeoutException {
      throw const ApiException('demo-rag did not answer in time.');
    } on http.ClientException {
      throw ApiException('Cannot reach demo-rag at $baseUrl. Is it running?');
    }
    if (r.statusCode == 200) return ChatAnswer.fromJson(jsonDecode(utf8.decode(r.bodyBytes)) as Map<String, dynamic>);
    throw _error(r);
  }

  /// Streams graph steps, then the final answer. Completing [stop] aborts the request.
  Stream<StreamEvent> stream(String question, Future<void> stop) async* {
    final uri = Uri.parse('$baseUrl/chat/stream').replace(queryParameters: {'question': question});
    final req = http.AbortableRequest('GET', uri, abortTrigger: stop)..headers['Accept'] = 'text/event-stream';
    final http.StreamedResponse resp;
    try {
      resp = await _http.send(req);
    } on http.RequestAbortedException {
      return;
    } on http.ClientException {
      throw ApiException('Cannot reach demo-rag at $baseUrl. Is it running?');
    }
    if (resp.statusCode != 200) {
      throw _error(await http.Response.fromStream(resp));
    }
    try {
      yield* parseSse(resp.stream.transform(utf8.decoder));
    } on http.RequestAbortedException {
      return;
    }
  }
}

/// Parses "event: x / data: {...}" blocks into stream events.
Stream<StreamEvent> parseSse(Stream<String> chunks) async* {
  var buffer = '';
  await for (final chunk in chunks) {
    buffer += chunk.replaceAll('\r\n', '\n');
    while (true) {
      final end = buffer.indexOf('\n\n');
      if (end < 0) break;
      final block = buffer.substring(0, end);
      buffer = buffer.substring(end + 2);
      String? name;
      final data = StringBuffer();
      for (final line in block.split('\n')) {
        if (line.startsWith('event:')) name = line.substring(6).trim();
        if (line.startsWith('data:')) data.write(line.substring(5).trim());
      }
      if (data.isEmpty) continue;
      final j = jsonDecode(data.toString()) as Map<String, dynamic>;
      if (name == 'final') {
        yield FinalEvent(ChatAnswer.fromJson(j));
      } else {
        yield StepEvent(
          j['node'] as String? ?? '?',
          [for (final e in (j['guard_events'] as List? ?? const [])) GuardEvent.fromJson(e as Map<String, dynamic>)],
        );
      }
    }
  }
}
