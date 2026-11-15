import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../theme/tokens.dart';

/// Small-caps label with a short rule in front: "— HANDMADE PASTA · BROOKLYN".
class Eyebrow extends StatelessWidget {
  const Eyebrow(this.text, {super.key, this.color = Palette.ink});
  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) => Row(mainAxisSize: MainAxisSize.min, children: [
        Container(width: 20, height: 1.2, color: color),
        const SizedBox(width: Space.x2 + 2),
        Flexible(child: Text(text.toUpperCase(), style: Typo.eyebrow.copyWith(color: color))),
      ]);
}

enum PillKind { primary, outline, quiet }

/// Rounded pill button. Primary is Tomato Red; outline is a hairline in ink.
class PillButton extends StatefulWidget {
  const PillButton({super.key, required this.label, required this.onPressed, this.kind = PillKind.primary, this.icon, this.loading = false, this.dense = false});
  final String label;
  final VoidCallback? onPressed;
  final PillKind kind;
  final IconData? icon;
  final bool loading;
  final bool dense;

  @override
  State<PillButton> createState() => _PillButtonState();
}

class _PillButtonState extends State<PillButton> {
  bool _hover = false;
  bool _focus = false;
  bool _down = false;

  @override
  Widget build(BuildContext context) {
    final enabled = widget.onPressed != null && !widget.loading;
    final (bg, fg, border) = switch (widget.kind) {
      PillKind.primary => (
          _hover || _down ? const Color(0xFFCC3420) : Palette.tomato,
          Palette.onTomato,
          Colors.transparent,
        ),
      PillKind.outline => (_hover ? Palette.ink.withValues(alpha: 0.06) : Colors.transparent, Palette.ink, Palette.ink.withValues(alpha: 0.55)),
      PillKind.quiet => (_hover ? Palette.ink.withValues(alpha: 0.06) : Colors.transparent, Palette.ink, Colors.transparent),
    };
    final pad = widget.dense
        ? const EdgeInsets.symmetric(horizontal: Space.x3 + 2, vertical: Space.x2)
        : const EdgeInsets.symmetric(horizontal: Space.x5 - 2, vertical: Space.x3 + 1);
    return Semantics(
      button: true,
      enabled: enabled,
      label: widget.label,
      child: FocusableActionDetector(
        enabled: enabled,
        mouseCursor: enabled ? SystemMouseCursors.click : SystemMouseCursors.basic,
        onShowHoverHighlight: (v) => setState(() => _hover = v),
        onShowFocusHighlight: (v) => setState(() => _focus = v),
        actions: {ActivateIntent: CallbackAction<ActivateIntent>(onInvoke: (_) => widget.onPressed?.call())},
        shortcuts: const {SingleActivator(LogicalKeyboardKey.enter): ActivateIntent()},
        child: GestureDetector(
          onTapDown: enabled ? (_) => setState(() => _down = true) : null,
          onTapCancel: () => setState(() => _down = false),
          onTapUp: enabled ? (_) => setState(() => _down = false) : null,
          onTap: enabled ? widget.onPressed : null,
          child: AnimatedOpacity(
            duration: const Duration(milliseconds: 120),
            opacity: enabled || widget.loading ? 1 : 0.45,
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 120),
              padding: pad,
              decoration: BoxDecoration(
                color: bg,
                borderRadius: BorderRadius.circular(Radii.pill),
                border: Border.all(color: border),
                boxShadow: _focus ? [const BoxShadow(color: Palette.ink, spreadRadius: 2)] : null,
              ),
              child: Row(mainAxisSize: MainAxisSize.min, children: [
                if (widget.loading)
                  Padding(
                    padding: const EdgeInsets.only(right: Space.x2),
                    child: SizedBox(width: 13, height: 13, child: CircularProgressIndicator(strokeWidth: 1.6, color: fg)),
                  )
                else if (widget.icon != null)
                  Padding(padding: const EdgeInsets.only(right: Space.x2 - 2), child: Icon(widget.icon, size: 15, color: fg)),
                Text(widget.label, style: Typo.button.copyWith(color: fg, fontSize: widget.dense ? 13 : 14.5)),
              ]),
            ),
          ),
        ),
      ),
    );
  }
}

/// The hand-drawn Tomato Red stroke under the italic word of the headline.
class ScribblePainter extends CustomPainter {
  const ScribblePainter({this.color = Palette.tomato});
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width, h = size.height;
    final p = Path()
      ..moveTo(w * 0.01, h * 0.62)
      ..cubicTo(w * 0.22, h * 0.30, w * 0.48, h * 0.42, w * 0.70, h * 0.38)
      ..cubicTo(w * 0.83, h * 0.36, w * 0.93, h * 0.30, w * 0.99, h * 0.22)
      ..moveTo(w * 0.10, h * 0.86)
      ..cubicTo(w * 0.34, h * 0.64, w * 0.62, h * 0.70, w * 0.86, h * 0.58);
    canvas.drawPath(
      p,
      Paint()
        ..color = color
        ..style = PaintingStyle.stroke
        ..strokeWidth = (h * 0.28).clamp(2.0, 4.0)
        ..strokeCap = StrokeCap.round,
    );
  }

  @override
  bool shouldRepaint(ScribblePainter old) => old.color != color;
}

/// "Text worth a *second* look." with the italic accent underlined by hand.
class AccentHeadline extends StatelessWidget {
  const AccentHeadline({super.key, required this.before, required this.accent, required this.after, this.size = 64});
  final String before;
  final String accent;
  final String after;
  final double size;

  @override
  Widget build(BuildContext context) {
    final base = Typo.display.copyWith(fontSize: size);
    final italic = Typo.displayItalic.copyWith(fontSize: size);
    return Semantics(
      header: true,
      label: '$before$accent$after',
      child: ExcludeSemantics(
        child: Text.rich(TextSpan(style: base, children: [
          TextSpan(text: before),
          WidgetSpan(
            alignment: PlaceholderAlignment.baseline,
            baseline: TextBaseline.alphabetic,
            child: Stack(clipBehavior: Clip.none, children: [
              Text(accent, style: italic),
              Positioned(left: -size * 0.04, right: -size * 0.02, bottom: -size * 0.16, height: size * 0.22, child: const CustomPaint(painter: ScribblePainter())),
            ]),
          ),
          TextSpan(text: after),
        ])),
      ),
    );
  }
}

/// Verdict chip: Tomato for injection, Sage for safe, an ink outline for scanner errors.
class VerdictChip extends StatelessWidget {
  const VerdictChip(this.verdict, {super.key, this.large = false});
  final String verdict;
  final bool large;

  @override
  Widget build(BuildContext context) {
    final (label, bg, fg, border) = switch (verdict) {
      'injection' => ('Injection', Palette.tomato, Palette.onTomato, Palette.tomato),
      'safe' => ('Safe', Palette.sage, Palette.ink, Palette.sage),
      _ => ('Scanner error', Colors.transparent, Palette.ink, Palette.ink),
    };
    return Container(
      key: const Key('verdict-chip'),
      padding: EdgeInsets.symmetric(horizontal: large ? Space.x3 + 2 : Space.x3, vertical: large ? 7 : 5),
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(Radii.pill), border: Border.all(color: border)),
      child: Text(label, style: Typo.label.copyWith(color: fg, fontSize: large ? 14 : 12.5, height: 1)),
    );
  }
}

/// Small rectangular tag, like the "Most ordered" label on a menu photo.
class Tag extends StatelessWidget {
  const Tag(this.text, {super.key, this.color = Palette.ink, this.fill = Colors.transparent});
  final String text;
  final Color color;
  final Color fill;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: Space.x2, vertical: 3),
        decoration: BoxDecoration(color: fill, borderRadius: BorderRadius.circular(4), border: Border.all(color: color.withValues(alpha: 0.35))),
        child: Text(text, style: Typo.small.copyWith(color: color, fontSize: 11.5, height: 1.2, fontWeight: FontWeight.w600)),
      );
}

/// Off-white card with a hairline border, used for every content block.
class PaperCard extends StatelessWidget {
  const PaperCard({super.key, required this.child, this.padding = const EdgeInsets.all(Space.x5), this.color = Palette.card});
  final Widget child;
  final EdgeInsets padding;
  final Color color;

  @override
  Widget build(BuildContext context) => Container(
        padding: padding,
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(Radii.card),
          border: Border.all(color: Palette.hairline),
        ),
        child: child,
      );
}

/// Section intro: eyebrow, serif title, one muted line ("The menu, short and loud.").
class SectionIntro extends StatelessWidget {
  const SectionIntro({super.key, required this.eyebrow, required this.title, this.copy});
  final String eyebrow;
  final String title;
  final String? copy;

  @override
  Widget build(BuildContext context) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Eyebrow(eyebrow, color: Palette.inkMuted),
        const SizedBox(height: Space.x3),
        Text(title, style: Typo.h1),
        if (copy != null) ...[const SizedBox(height: Space.x3), Text(copy!, style: Typo.bodyMuted)],
      ]);
}

/// Plain-language meaning of an action, for people who do not know the API.
String actionMeaning(String action) => switch (action) {
      'block' => 'The message would be refused before it reaches the model.',
      'drop_chunk' => 'The document chunk would be left out of the prompt and quarantined.',
      'redact_tool_output' => 'The tool result would be replaced with a redaction note.',
      'log_only' => 'Monitoring mode: the text passes, and the verdict is only logged.',
      _ => 'The text can go to the model as is.',
    };

String attackLabel(String? type) => switch (type) {
      'override' => 'Instruction override',
      'persona' => 'Persona switch',
      'prompt_leak' => 'Prompt leak',
      'exfiltration' => 'Data exfiltration',
      'tool_abuse' => 'Tool abuse',
      _ => 'None',
    };

String langLabel(String lang) => switch (lang) {
      'en' => 'English',
      'ru_mix' => 'Roman Urdu, mixed',
      'ru_pure' => 'Roman Urdu',
      _ => lang,
    };
