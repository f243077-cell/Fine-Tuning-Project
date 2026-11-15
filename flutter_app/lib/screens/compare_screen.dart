import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../main.dart';
import '../state/providers.dart';
import '../theme/tokens.dart';
import '../widgets/events.dart';
import '../widgets/ui.dart';

/// The same question through demo-rag twice: guard off, then guard on (needs ALLOW_GUARD_TOGGLE=true).
class CompareScreen extends ConsumerStatefulWidget {
  const CompareScreen({super.key});

  @override
  ConsumerState<CompareScreen> createState() => _CompareScreenState();
}

class _CompareScreenState extends ConsumerState<CompareScreen> {
  final _controller = TextEditingController();
  int _revision = -1;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final s = ref.watch(compareProvider);
    if (s.revision != _revision) {
      _revision = s.revision;
      if (_controller.text != s.question) _controller.text = s.question;
    }
    final c = ref.read(compareProvider.notifier);
    final wide = MediaQuery.sizeOf(context).width >= 900;
    return PageFrame(children: [
      Flex(direction: wide ? Axis.horizontal : Axis.vertical, crossAxisAlignment: CrossAxisAlignment.end, children: [
        Flexible(
          flex: wide ? 5 : 0,
          fit: FlexFit.loose,
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Eyebrow('Same question, two pipelines', color: Palette.inkMuted),
            const SizedBox(height: Space.x4),
            AccentHeadline(before: 'Guard ', accent: 'off', after: ', guard on.', size: wide ? 52 : 40),
            const SizedBox(height: Space.x4),
            Text(
              'The reference RAG app answers from a small help centre about a fictional shop. Ask it something, '
              'or paste an attack, and see what each version lets through.',
              style: Typo.bodyMuted,
            ),
          ]),
        ),
        SizedBox(width: wide ? Space.x7 : 0, height: wide ? 0 : Space.x5),
        Flexible(
          flex: wide ? 6 : 0,
          fit: FlexFit.loose,
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            TextField(
              controller: _controller,
              onChanged: c.setQuestion,
              minLines: 2,
              maxLines: 4,
              style: Typo.body,
              decoration: const InputDecoration(hintText: 'Ask a question, or paste an attack'),
            ),
            const SizedBox(height: Space.x3),
            Row(children: [
              Expanded(child: Text('Guard off runs first, then guard on. On a laptop CPU each answer takes a while.', style: Typo.small)),
              const SizedBox(width: Space.x3),
              PillButton(
                label: s.running ? 'Running' : 'Run both',
                loading: s.running,
                onPressed: s.question.trim().isEmpty ? null : c.run,
              ),
            ]),
          ]),
        ),
      ]),
      const SizedBox(height: Space.x7),
      Flex(direction: wide ? Axis.horizontal : Axis.vertical, crossAxisAlignment: CrossAxisAlignment.start, children: [
        Flexible(fit: FlexFit.loose, child: _SideCard(title: 'Guard off', subtitle: 'No checks. Whatever retrieval finds goes into the prompt.', side: s.off, protected: false)),
        SizedBox(width: wide ? Space.x5 : 0, height: wide ? 0 : Space.x5),
        Flexible(fit: FlexFit.loose, child: _SideCard(title: 'Guard on', subtitle: 'Question, documents, and answer are checked.', side: s.on, protected: true)),
      ]),
    ]);
  }
}

class _SideCard extends StatelessWidget {
  const _SideCard({required this.title, required this.subtitle, required this.side, required this.protected});
  final String title;
  final String subtitle;
  final CompareSide side;
  final bool protected;

  @override
  Widget build(BuildContext context) {
    final a = side.answer;
    return PaperCard(
      color: protected ? Palette.card : Palette.paper,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Text(title, style: Typo.h2),
          const SizedBox(width: Space.x3),
          Tag(protected ? 'protected' : 'unprotected',
              color: protected ? Palette.sageDeep : Palette.tomato, fill: protected ? Palette.sageTint : Palette.tomatoTint),
        ]),
        const SizedBox(height: Space.x2),
        Text(subtitle, style: Typo.small),
        const SizedBox(height: Space.x4),
        const Divider(),
        const SizedBox(height: Space.x4),
        if (side.loading)
          Row(children: [
            const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 1.6, color: Palette.inkMuted)),
            const SizedBox(width: Space.x3),
            Text('Waiting for the answer…', style: Typo.bodyMuted),
          ])
        else if (side.error != null)
          Text(side.error!, style: Typo.body.copyWith(color: Palette.tomato))
        else if (a == null)
          Text('Not run yet.', style: Typo.bodyMuted)
        else ...[
          if (a.blocked || a.refused != null)
            Padding(
              padding: const EdgeInsets.only(bottom: Space.x3),
              child: Tag(a.blocked ? 'Blocked at the question check' : 'Refused after the answer check',
                  color: Palette.tomato, fill: Palette.tomatoTint),
            ),
          Text(a.answer, style: Typo.body.copyWith(fontSize: 15.5, height: 1.55)),
          if (a.sources.isNotEmpty) ...[const SizedBox(height: Space.x4), CitationChips(sources: a.sources)],
          if (protected) ...[
            const SizedBox(height: Space.x5),
            Text('WHAT THE GUARD DID', style: Typo.eyebrow.copyWith(color: Palette.inkMuted)),
            const SizedBox(height: Space.x2),
            GuardTrail(events: a.events),
          ],
        ],
      ]),
    );
  }
}

/// Used by the library to send a sample here.
void openInCompare(WidgetRef ref, Sample s) {
  ref.read(compareProvider.notifier).loadSample(s);
  ref.read(tabProvider.notifier).go(AppTab.compare);
}

