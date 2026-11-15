import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../main.dart';
import '../state/providers.dart';
import '../theme/tokens.dart';
import '../widgets/ui.dart';
import 'compare_screen.dart';

enum _Filter {
  all('All'),
  attacks('Attacks'),
  benign('Look-alikes'),
  english('English'),
  romanUrdu('Roman Urdu');

  const _Filter(this.label);
  final String label;
}

/// Built-in sample attacks and benign look-alikes, laid out like a short menu.
class LibraryScreen extends ConsumerStatefulWidget {
  const LibraryScreen({super.key});

  @override
  ConsumerState<LibraryScreen> createState() => _LibraryScreenState();
}

class _LibraryScreenState extends ConsumerState<LibraryScreen> {
  _Filter _filter = _Filter.all;

  bool _keep(Sample s) => switch (_filter) {
        _Filter.all => true,
        _Filter.attacks => s.isAttack,
        _Filter.benign => !s.isAttack,
        _Filter.english => s.lang == 'en',
        _Filter.romanUrdu => s.lang != 'en',
      };

  @override
  Widget build(BuildContext context) {
    final samples = ref.watch(samplesProvider);
    final width = MediaQuery.sizeOf(context).width;
    final cols = width >= 1100 ? 3 : (width >= 700 ? 2 : 1);
    return PageFrame(children: [
      const SectionIntro(
        eyebrow: 'Attack library',
        title: 'The attacks, short and loud.',
        copy: 'Harmless stand-ins for real attacks (a secret word, a fake link, a tool that does not exist), plus '
            'everyday questions that only look suspicious. Send any of them to the scanner or the comparison.',
      ),
      const SizedBox(height: Space.x5),
      Wrap(spacing: Space.x2, runSpacing: Space.x2, children: [
        for (final f in _Filter.values)
          PillButton(
            label: f.label,
            dense: true,
            kind: f == _filter ? PillKind.primary : PillKind.outline,
            onPressed: () => setState(() => _filter = f),
          ),
      ]),
      const SizedBox(height: Space.x5),
      samples.when(
        loading: () => const Padding(padding: EdgeInsets.all(Space.x6), child: Center(child: CircularProgressIndicator(color: Palette.inkMuted))),
        error: (e, _) => Text('Could not load the samples: $e', style: Typo.body),
        data: (all) {
          final items = all.where(_keep).toList();
          final rows = <Widget>[];
          for (var i = 0; i < items.length; i += cols) {
            final slice = items.sublist(i, (i + cols).clamp(0, items.length));
            rows.add(IntrinsicHeight(
              child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                for (var j = 0; j < cols; j++) ...[
                  if (j > 0) const SizedBox(width: Space.x4),
                  Expanded(child: j < slice.length ? _SampleCard(sample: slice[j]) : const SizedBox()),
                ],
              ]),
            ));
            rows.add(const SizedBox(height: Space.x4));
          }
          return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: rows);
        },
      ),
    ]);
  }
}

class _SampleCard extends ConsumerWidget {
  const _SampleCard({required this.sample});
  final Sample sample;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final s = sample;
    return PaperCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Tag(s.isAttack ? attackLabel(s.kind) : 'Benign look-alike',
              color: s.isAttack ? Palette.tomato : Palette.sageDeep, fill: s.isAttack ? Palette.tomatoTint : Palette.sageTint),
          const Spacer(),
          Text(langLabel(s.lang), style: Typo.small.copyWith(fontSize: 12)),
        ]),
        const SizedBox(height: Space.x4),
        Text(s.title, style: Typo.h3),
        const SizedBox(height: Space.x2),
        Expanded(
          child: Text('“${s.text}”', maxLines: 5, overflow: TextOverflow.ellipsis, style: Typo.bodyMuted.copyWith(fontSize: 14, height: 1.5)),
        ),
        const SizedBox(height: Space.x4),
        const Divider(),
        const SizedBox(height: Space.x3),
        Row(children: [
          Expanded(child: Text(s.source.label, style: Typo.small.copyWith(fontSize: 12))),
          PillButton(label: 'Compare', kind: PillKind.outline, dense: true, onPressed: () => openInCompare(ref, s)),
          const SizedBox(width: Space.x2),
          PillButton(label: 'Scan', dense: true, onPressed: () {
            ref.read(scanProvider.notifier).loadSample(s);
            ref.read(tabProvider.notifier).go(AppTab.scan);
          }),
        ]),
      ]),
    );
  }
}
