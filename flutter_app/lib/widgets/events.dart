import 'package:flutter/material.dart';

import '../api/models.dart';
import '../theme/tokens.dart';
import 'ui.dart';

String checkpointName(String cp) => switch (cp) {
      'G1' => 'Question check',
      'G2' => 'Document check',
      'G4' => 'Answer check',
      _ => cp,
    };

/// What each guard checkpoint did, one hairline row per checkpoint (G2 rows are grouped).
class GuardTrail extends StatelessWidget {
  const GuardTrail({super.key, required this.events});
  final List<GuardEvent> events;

  @override
  Widget build(BuildContext context) {
    if (events.isEmpty) {
      return Text('No guard checks ran.', style: Typo.small);
    }
    final rows = <Widget>[];
    for (final cp in ['G1', 'G2', 'G4']) {
      final evs = events.where((e) => e.checkpoint == cp).toList();
      if (evs.isEmpty) continue;
      final stopped = evs.where((e) => e.stopped).toList();
      final detail = switch (cp) {
        'G2' => stopped.isEmpty ? '${evs.length} documents passed' : '${stopped.length} of ${evs.length} documents dropped',
        'G4' => stopped.isEmpty ? 'citations and canary fine' : 'rejected: ${evs.last.reason ?? evs.last.action}',
        _ => stopped.isEmpty ? 'passed' : 'blocked as ${attackLabel(stopped.first.attackType).toLowerCase()}',
      };
      rows.add(Padding(
        padding: const EdgeInsets.symmetric(vertical: Space.x2),
        child: Row(children: [
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(shape: BoxShape.circle, color: stopped.isEmpty ? Palette.sage : Palette.tomato),
          ),
          const SizedBox(width: Space.x3),
          SizedBox(width: 34, child: Text(cp, style: Typo.label.copyWith(fontSize: 12))),
          Text(checkpointName(cp), style: Typo.small.copyWith(color: Palette.ink)),
          const SizedBox(width: Space.x2),
          Expanded(child: Text(detail, textAlign: TextAlign.right, style: Typo.small)),
        ]),
      ));
    }
    return Column(children: rows);
  }
}

/// Source chips under an answer: "[en-02-refund-policy] Refund policy".
class CitationChips extends StatelessWidget {
  const CitationChips({super.key, required this.sources});
  final List<Citation> sources;

  @override
  Widget build(BuildContext context) => Wrap(spacing: Space.x2, runSpacing: Space.x2, children: [
        for (final c in sources)
          Tooltip(
            message: c.docId,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: Space.x3, vertical: 5),
              decoration: BoxDecoration(
                color: Palette.sageTint,
                borderRadius: BorderRadius.circular(Radii.pill),
                border: Border.all(color: Palette.sage),
              ),
              child: Text(c.title, style: Typo.small.copyWith(color: Palette.sageDeep, fontWeight: FontWeight.w600, fontSize: 12)),
            ),
          ),
      ]);
}
