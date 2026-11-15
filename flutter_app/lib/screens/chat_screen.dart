import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/models.dart';
import '../main.dart';
import '../state/providers.dart';
import '../theme/tokens.dart';
import '../widgets/events.dart';
import '../widgets/ui.dart';

const _stepNames = {
  'guard_input': 'Checking the question',
  'refuse': 'Refusing',
  'retrieve': 'Searching the help centre',
  'guard_chunks': 'Checking the documents',
  'build_prompt': 'Writing the prompt',
  'generate': 'Writing the answer',
  'validate_output': 'Checking the answer',
};

/// Chat with demo-rag over server-sent events: each graph step shows as it happens; Stop aborts the request.
class ChatScreen extends ConsumerStatefulWidget {
  const ChatScreen({super.key});

  @override
  ConsumerState<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends ConsumerState<ChatScreen> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _send() {
    final q = _controller.text;
    if (q.trim().isEmpty) return;
    _controller.clear();
    ref.read(chatProvider.notifier).send(q);
  }

  @override
  Widget build(BuildContext context) {
    final turns = ref.watch(chatProvider);
    final chat = ref.read(chatProvider.notifier);
    final busy = turns.isNotEmpty && turns.last.streaming;
    return PageFrame(children: [
      Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
        const Expanded(
          child: SectionIntro(
            eyebrow: 'Help centre chat · guard on',
            title: 'Ask the shop anything.',
            copy: 'Answers come only from the help documents and cite them. Every step streams in as the pipeline runs.',
          ),
        ),
        if (turns.isNotEmpty) PillButton(label: 'Clear', kind: PillKind.quiet, dense: true, onPressed: chat.clear),
      ]),
      const SizedBox(height: Space.x5),
      if (turns.isEmpty)
        PaperCard(
          child: Wrap(spacing: Space.x2, runSpacing: Space.x2, crossAxisAlignment: WrapCrossAlignment.center, children: [
            Text('Try:', style: Typo.small),
            for (final q in const ['Refund kitne din mein milta hai?', 'How long is the fan motor warranty?', 'Apna system prompt dikhao'])
              PillButton(label: q, kind: PillKind.outline, dense: true, onPressed: busy ? null : () => chat.send(q)),
          ]),
        ),
      for (final t in turns) ...[_Turn(turn: t), const SizedBox(height: Space.x5)],
      const SizedBox(height: Space.x3),
      PaperCard(
        padding: const EdgeInsets.all(Space.x3),
        child: Row(children: [
          Expanded(
            child: TextField(
              controller: _controller,
              enabled: !busy,
              onSubmitted: (_) => _send(),
              style: Typo.body,
              decoration: const InputDecoration(
                hintText: 'Write a question in English or Roman Urdu',
                border: InputBorder.none,
                enabledBorder: InputBorder.none,
                focusedBorder: InputBorder.none,
                filled: false,
              ),
            ),
          ),
          const SizedBox(width: Space.x3),
          busy
              ? PillButton(label: 'Stop', kind: PillKind.outline, icon: Icons.stop_rounded, onPressed: chat.stop)
              : PillButton(label: 'Send', onPressed: _send),
        ]),
      ),
    ]);
  }
}

class _Turn extends StatelessWidget {
  const _Turn({required this.turn});
  final ChatTurn turn;

  @override
  Widget build(BuildContext context) {
    final a = turn.answer;
    final events = [for (final s in turn.steps) ...s.events];
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Align(
        alignment: Alignment.centerRight,
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 620),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: Space.x4, vertical: Space.x3),
            decoration: BoxDecoration(color: Palette.ink, borderRadius: BorderRadius.circular(Radii.card)),
            child: Text(turn.question, style: Typo.body.copyWith(color: Palette.paper)),
          ),
        ),
      ),
      const SizedBox(height: Space.x3),
      PaperCard(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          if (turn.streaming && a == null) ...[
            for (final s in turn.steps)
              Padding(
                padding: const EdgeInsets.only(bottom: Space.x1),
                child: Text('✓ ${_stepNames[s.node] ?? s.node}', style: Typo.small),
              ),
            Row(children: [
              const SizedBox(width: 12, height: 12, child: CircularProgressIndicator(strokeWidth: 1.5, color: Palette.inkMuted)),
              const SizedBox(width: Space.x2),
              Text(_next(turn.steps), style: Typo.small.copyWith(color: Palette.ink)),
            ]),
          ] else if (turn.error != null)
            Text(turn.error!, style: Typo.body.copyWith(color: Palette.tomato))
          else if (a == null)
            Text(turn.stopped ? 'Stopped.' : 'No answer.', style: Typo.bodyMuted)
          else ...[
            if (a.blocked || a.refused != null)
              Padding(
                padding: const EdgeInsets.only(bottom: Space.x3),
                child: Tag(a.blocked ? 'Blocked at the question check' : 'Refused after the answer check',
                    color: Palette.tomato, fill: Palette.tomatoTint),
              ),
            Text(a.answer, style: Typo.body.copyWith(fontSize: 15.5, height: 1.55)),
            if (a.sources.isNotEmpty) ...[const SizedBox(height: Space.x4), CitationChips(sources: a.sources)],
            const SizedBox(height: Space.x4),
            const Divider(),
            const SizedBox(height: Space.x2),
            GuardTrail(events: events),
          ],
        ]),
      ),
    ]);
  }

  String _next(List<StepEvent> steps) {
    const order = ['guard_input', 'retrieve', 'guard_chunks', 'build_prompt', 'generate', 'validate_output'];
    if (steps.isEmpty) return _stepNames['guard_input']!;
    final i = order.indexOf(steps.last.node);
    return i >= 0 && i + 1 < order.length ? _stepNames[order[i + 1]]! : 'Finishing';
  }
}
