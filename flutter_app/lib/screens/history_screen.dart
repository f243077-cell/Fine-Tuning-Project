import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../main.dart';
import '../state/providers.dart';
import '../theme/tokens.dart';
import '../widgets/ui.dart';

/// Scans from this session only (Riverpod state; nothing is stored on disk).
class HistoryScreen extends ConsumerWidget {
  const HistoryScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final items = ref.watch(historyProvider);
    final flagged = items.where((e) => e.result.isInjection).length;
    final lat = [for (final e in items) e.result.latencyMs]..sort();
    final median = lat.isEmpty ? null : lat[lat.length ~/ 2];
    final wide = MediaQuery.sizeOf(context).width >= 760;
    return PageFrame(children: [
      Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
        const Expanded(
          child: SectionIntro(
            eyebrow: 'This session',
            title: 'Everything you scanned.',
            copy: 'Kept in memory while the app is open. Close the tab and it is gone.',
          ),
        ),
        if (items.isNotEmpty)
          PillButton(label: 'Clear history', kind: PillKind.outline, dense: true, onPressed: ref.read(historyProvider.notifier).clear),
      ]),
      const SizedBox(height: Space.x5),
      PaperCard(
        child: Wrap(spacing: Space.x7, runSpacing: Space.x4, children: [
          _Figure(value: '${items.length}', label: 'scans'),
          _Figure(value: '$flagged', label: 'flagged as injection'),
          _Figure(value: '${items.length - flagged}', label: 'safe or error'),
          _Figure(value: median == null ? '—' : '$median', label: 'ms median time'),
        ]),
      ),
      const SizedBox(height: Space.x5),
      if (items.isEmpty)
        Text('No scans yet.', style: Typo.bodyMuted)
      else
        PaperCard(
          padding: const EdgeInsets.symmetric(horizontal: Space.x5, vertical: Space.x2),
          child: Column(children: [
            for (var i = 0; i < items.length; i++)
              Container(
                padding: const EdgeInsets.symmetric(vertical: Space.x3),
                decoration: BoxDecoration(border: i == items.length - 1 ? null : const Border(bottom: BorderSide(color: Palette.hairline))),
                child: Row(children: [
                  SizedBox(width: 60, child: Text(_time(items[i].at), style: Typo.small)),
                  SizedBox(width: 110, child: Align(alignment: Alignment.centerLeft, child: VerdictChip(items[i].result.verdict))),
                  if (wide) SizedBox(width: 150, child: Text(attackLabel(items[i].result.attackType), style: Typo.small.copyWith(color: Palette.ink))),
                  Expanded(child: Text(items[i].text, maxLines: 1, overflow: TextOverflow.ellipsis, style: Typo.body)),
                  const SizedBox(width: Space.x4),
                  Text('${items[i].result.latencyMs} ms', style: Typo.small),
                ]),
              ),
          ]),
        ),
    ]);
  }

  String _time(DateTime t) => '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';
}

class _Figure extends StatelessWidget {
  const _Figure({required this.value, required this.label});
  final String value;
  final String label;

  @override
  Widget build(BuildContext context) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(value, style: Typo.figure.copyWith(fontSize: 38)),
        const SizedBox(height: Space.x1),
        Text(label, style: Typo.small),
      ]);
}
