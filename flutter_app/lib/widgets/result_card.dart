import 'package:flutter/material.dart';

import '../api/models.dart';
import '../theme/tokens.dart';
import 'ui.dart';

/// Result of one scan: verdict chip, attack type, action, latency in ms. No confidence percentage (PRD FR-2).
class ResultCard extends StatelessWidget {
  const ResultCard({super.key, required this.result, required this.text, required this.source});
  final ScanResult result;
  final String text;
  final Source source;

  @override
  Widget build(BuildContext context) {
    final flagged = result.isInjection;
    final headline = switch (result.verdict) {
      'injection' => attackLabel(result.attackType),
      'safe' => 'Nothing aimed at the model',
      _ => 'The guard could not decide',
    };
    final band = flagged ? Palette.tomatoTint : (result.isError ? Palette.paper : Palette.sageTint);
    return PaperCard(
      padding: EdgeInsets.zero,
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Container(
          padding: const EdgeInsets.fromLTRB(Space.x5, Space.x5, Space.x5, Space.x4),
          decoration: BoxDecoration(
            color: band,
            borderRadius: const BorderRadius.vertical(top: Radius.circular(Radii.card - 1)),
          ),
          child: LayoutBuilder(builder: (context, c) {
            final narrow = c.maxWidth < 460;
            final left = Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                VerdictChip(result.verdict, large: true),
                const SizedBox(width: Space.x3),
                Flexible(child: Text(source.label.toUpperCase(), style: Typo.eyebrow.copyWith(color: Palette.inkMuted))),
              ]),
              const SizedBox(height: Space.x4),
              Text(headline, key: const Key('result-headline'), style: Typo.h2),
              const SizedBox(height: Space.x2),
              Text(
                result.isError ? 'Scanner error: ${result.scannerError}. ${actionMeaning(result.action)}' : actionMeaning(result.action),
                style: Typo.bodyMuted,
              ),
            ]);
            final figure = Column(crossAxisAlignment: narrow ? CrossAxisAlignment.start : CrossAxisAlignment.end, children: [
              Text('${result.latencyMs}', key: const Key('result-latency'), style: Typo.figure),
              const SizedBox(height: Space.x1),
              Text('ms to decide', style: Typo.small),
            ]);
            return narrow
                ? Column(crossAxisAlignment: CrossAxisAlignment.start, children: [left, const SizedBox(height: Space.x4), figure])
                : Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Expanded(child: left),
                    const SizedBox(width: Space.x5),
                    figure,
                  ]);
          }),
        ),
        const Divider(),
        Padding(
          padding: const EdgeInsets.fromLTRB(Space.x5, Space.x3, Space.x5, Space.x2),
          child: Column(children: [
            _Row('Action', result.action.replaceAll('_', ' '), key: const Key('result-action')),
            _Row('Attack type', result.attackType ?? '—'),
            _Row('Windows scanned', '${result.windows}'),
            _Row('Model', result.model),
            _Row('Request', result.requestId.length > 12 ? result.requestId.substring(0, 12) : result.requestId, mono: true, last: true),
          ]),
        ),
        Container(
          margin: const EdgeInsets.fromLTRB(Space.x5, 0, Space.x5, Space.x5),
          padding: const EdgeInsets.only(left: Space.x3),
          decoration: BoxDecoration(border: Border(left: BorderSide(color: flagged ? Palette.tomato : Palette.sage, width: 2))),
          child: Text(text, maxLines: 4, overflow: TextOverflow.ellipsis, style: Typo.bodyMuted.copyWith(fontStyle: FontStyle.italic)),
        ),
      ]),
    );
  }
}

class _Row extends StatelessWidget {
  const _Row(this.label, this.value, {super.key, this.mono = false, this.last = false});
  final String label;
  final String value;
  final bool mono;
  final bool last;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(vertical: Space.x2 + 1),
        decoration: BoxDecoration(border: last ? null : const Border(bottom: BorderSide(color: Palette.hairline))),
        child: Row(children: [
          Expanded(child: Text(label, style: Typo.small)),
          Text(value, style: mono ? Typo.mono.copyWith(color: Palette.ink) : Typo.label),
        ]),
      );
}
