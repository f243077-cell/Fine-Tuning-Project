import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'screens/chat_screen.dart';
import 'screens/compare_screen.dart';
import 'screens/history_screen.dart';
import 'screens/library_screen.dart';
import 'screens/scan_screen.dart';
import 'state/providers.dart';
import 'theme/app_theme.dart';
import 'theme/tokens.dart';
import 'widgets/ui.dart';

void main() => runApp(const ProviderScope(child: PlaygroundApp()));

class PlaygroundApp extends StatelessWidget {
  const PlaygroundApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'RU-Guard playground',
        debugShowCheckedModeBanner: false,
        theme: buildTheme(),
        home: const AppShell(),
      );
}

const maxContentWidth = 1180.0;

class AppShell extends ConsumerWidget {
  const AppShell({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tab = ref.watch(tabProvider);
    final body = switch (tab) {
      AppTab.scan => const ScanScreen(),
      AppTab.compare => const CompareScreen(),
      AppTab.chat => const ChatScreen(),
      AppTab.library => const LibraryScreen(),
      AppTab.history => const HistoryScreen(),
    };
    return Scaffold(
      body: SafeArea(
        child: Column(children: [
          const TopBar(),
          const Divider(),
          Expanded(
            child: AnimatedSwitcher(
              duration: const Duration(milliseconds: 180),
              layoutBuilder: (current, previous) => Stack(alignment: Alignment.topCenter, children: [...previous, ?current]),
              child: KeyedSubtree(key: ValueKey(tab), child: body),
            ),
          ),
        ]),
      ),
    );
  }
}

/// Wordmark, section links, guard status, and the one red call to action.
class TopBar extends ConsumerWidget {
  const TopBar({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tab = ref.watch(tabProvider);
    final health = ref.watch(healthProvider);
    final narrow = MediaQuery.sizeOf(context).width < 860;
    final links = [
      for (final t in AppTab.values) _NavLink(label: t.label, active: t == tab, onTap: () => ref.read(tabProvider.notifier).go(t)),
    ];
    final status = health.when(
      data: (h) => _Status(ok: h.ok, text: h.ok ? (narrow ? 'Online' : 'Guard online · ${h.model}') : 'Guard offline'),
      loading: () => const _Status(ok: null, text: 'Checking guard…'),
      error: (_, _) => const _Status(ok: false, text: 'Guard offline'),
    );
    final wordmark = Row(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.baseline, textBaseline: TextBaseline.alphabetic, children: [
      Text('RU-Guard', style: Typo.h3.copyWith(fontSize: 25, fontStyle: FontStyle.italic)),
      const SizedBox(width: Space.x2),
      Text('PLAYGROUND', style: Typo.eyebrow.copyWith(fontSize: 9.5, color: Palette.inkMuted)),
    ]);
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: maxContentWidth),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: Space.x5, vertical: Space.x4),
          child: narrow
              ? Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Row(children: [
                    wordmark,
                    const SizedBox(width: Space.x3),
                    Expanded(
                      child: Align(
                        alignment: Alignment.centerRight,
                        child: GestureDetector(onTap: () => ref.invalidate(healthProvider), child: status),
                      ),
                    ),
                  ]),
                  const SizedBox(height: Space.x3),
                  SingleChildScrollView(scrollDirection: Axis.horizontal, child: Row(children: links)),
                ])
              : Row(children: [
                  wordmark,
                  const SizedBox(width: Space.x7),
                  ...links,
                  const Spacer(),
                  Tooltip(message: 'Check again', child: GestureDetector(onTap: () => ref.invalidate(healthProvider), child: status)),
                  const SizedBox(width: Space.x4),
                  PillButton(label: 'Try an attack', dense: true, onPressed: () => ref.read(tabProvider.notifier).go(AppTab.library)),
                ]),
        ),
      ),
    );
  }
}

class _NavLink extends StatefulWidget {
  const _NavLink({required this.label, required this.active, required this.onTap});
  final String label;
  final bool active;
  final VoidCallback onTap;

  @override
  State<_NavLink> createState() => _NavLinkState();
}

class _NavLinkState extends State<_NavLink> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(right: Space.x5),
        child: MouseRegion(
          cursor: SystemMouseCursors.click,
          onEnter: (_) => setState(() => _hover = true),
          onExit: (_) => setState(() => _hover = false),
          child: Semantics(
            button: true,
            selected: widget.active,
            child: GestureDetector(
              onTap: widget.onTap,
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                Text(widget.label,
                    style: Typo.label.copyWith(
                      fontWeight: widget.active ? FontWeight.w600 : FontWeight.w500,
                      color: widget.active || _hover ? Palette.ink : Palette.inkMuted,
                    )),
                const SizedBox(height: 5),
                AnimatedContainer(
                  duration: const Duration(milliseconds: 160),
                  height: 2,
                  width: widget.active ? 18 : 0,
                  color: Palette.tomato,
                ),
              ]),
            ),
          ),
        ),
      );
}

class _Status extends StatelessWidget {
  const _Status({required this.ok, required this.text});
  final bool? ok;
  final String text;

  @override
  Widget build(BuildContext context) => Row(mainAxisSize: MainAxisSize.min, children: [
        Container(
          width: 7,
          height: 7,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: ok == null ? Palette.hairline : (ok! ? const Color(0xFF5E8B4A) : Palette.tomato),
          ),
        ),
        const SizedBox(width: Space.x2),
        Flexible(child: Text(text, overflow: TextOverflow.ellipsis, style: Typo.small.copyWith(fontSize: 12.5))),
      ]);
}

/// Centered page with the shared max width and side gutters.
class PageFrame extends StatelessWidget {
  const PageFrame({super.key, required this.children});
  final List<Widget> children;

  @override
  Widget build(BuildContext context) => SingleChildScrollView(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: maxContentWidth),
            child: Padding(
              padding: const EdgeInsets.fromLTRB(Space.x5, Space.x5, Space.x5, Space.x8),
              child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: children),
            ),
          ),
        ),
      );
}
