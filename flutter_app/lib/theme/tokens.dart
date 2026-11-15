import 'package:flutter/material.dart';

/// Palette fixed by the owner (Sage, Off-White, Tomato Red) plus the neutrals derived from it.
abstract final class Palette {
  static const sage = Color(0xFF9CAF88);
  static const paper = Color(0xFFF7F5EF); // Off-White
  static const tomato = Color(0xFFE8412C);

  static const ink = Color(0xFF1E2620); // body text, also used on sage
  static const inkMuted = Color(0xFF5C6358);
  static const sageDeep = Color(0xFF4E6141); // sage-family text on paper (contrast 6.4:1)
  static const sageTint = Color(0xFFE6ECDF); // quiet fills for safe states
  static const tomatoTint = Color(0xFFFBE3DF); // quiet fills for flagged states
  static const card = Color(0xFFFDFCF8);
  static const hairline = Color(0xFFDDD8CB);
  static const onTomato = Color(0xFFFFFFFF);
}

/// 4-px spacing grid.
abstract final class Space {
  static const x1 = 4.0;
  static const x2 = 8.0;
  static const x3 = 12.0;
  static const x4 = 16.0;
  static const x5 = 24.0;
  static const x6 = 32.0;
  static const x7 = 48.0;
  static const x8 = 64.0;
}

abstract final class Radii {
  static const card = 14.0;
  static const panel = 20.0;
  static const pill = 999.0;
}

const serif = 'InstrumentSerif';
const sans = 'InstrumentSans';

TextStyle _sans(double size, FontWeight w, {Color color = Palette.ink, double height = 1.45, double spacing = 0}) =>
    TextStyle(
      fontFamily: sans,
      fontSize: size,
      fontWeight: w,
      fontVariations: [FontVariation('wght', w.value.toDouble())],
      color: color,
      height: height,
      letterSpacing: spacing,
    );

/// Type scale: one display serif, one sans for everything else.
abstract final class Typo {
  static const display = TextStyle(fontFamily: serif, fontSize: 64, height: 1.0, color: Palette.ink, letterSpacing: -1.2);
  static const displayItalic =
      TextStyle(fontFamily: serif, fontStyle: FontStyle.italic, fontSize: 64, height: 1.0, color: Palette.ink, letterSpacing: -1.2);
  static const h1 = TextStyle(fontFamily: serif, fontSize: 40, height: 1.05, color: Palette.ink, letterSpacing: -0.6);
  static const h2 = TextStyle(fontFamily: serif, fontSize: 28, height: 1.1, color: Palette.ink, letterSpacing: -0.3);
  static const h3 = TextStyle(fontFamily: serif, fontSize: 21, height: 1.15, color: Palette.ink);
  static const figure = TextStyle(fontFamily: serif, fontSize: 44, height: 1.0, color: Palette.ink, letterSpacing: -0.8);

  static final body = _sans(15, FontWeight.w400);
  static final bodyMuted = _sans(15, FontWeight.w400, color: Palette.inkMuted);
  static final small = _sans(13, FontWeight.w400, color: Palette.inkMuted);
  static final label = _sans(13, FontWeight.w600);
  static final button = _sans(14.5, FontWeight.w600, height: 1.0);
  static final eyebrow = _sans(11, FontWeight.w600, spacing: 1.8, height: 1.0);
  static final mono = const TextStyle(fontFamily: 'monospace', fontSize: 12.5, color: Palette.inkMuted, height: 1.4);
}
