import 'package:flutter/material.dart';

import 'tokens.dart';

ThemeData buildTheme() {
  final scheme = ColorScheme.fromSeed(
    seedColor: Palette.sage,
    brightness: Brightness.light,
  ).copyWith(
    primary: Palette.tomato,
    onPrimary: Palette.onTomato,
    secondary: Palette.sage,
    onSecondary: Palette.ink,
    surface: Palette.paper,
    onSurface: Palette.ink,
    outline: Palette.hairline,
    error: Palette.tomato,
  );
  final hairline = OutlineInputBorder(
    borderRadius: BorderRadius.circular(10),
    borderSide: const BorderSide(color: Palette.hairline),
  );
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: Palette.paper,
    fontFamily: sans,
    textTheme: TextTheme(bodyMedium: Typo.body, bodySmall: Typo.small, labelLarge: Typo.button),
    splashFactory: NoSplash.splashFactory,
    dividerTheme: const DividerThemeData(color: Palette.hairline, thickness: 1, space: 1),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: Palette.card,
      hintStyle: Typo.bodyMuted,
      contentPadding: const EdgeInsets.all(Space.x4),
      border: hairline,
      enabledBorder: hairline,
      focusedBorder: hairline.copyWith(borderSide: const BorderSide(color: Palette.ink, width: 1.4)),
    ),
    textSelectionTheme: TextSelectionThemeData(
      cursorColor: Palette.tomato,
      selectionColor: Palette.sage.withValues(alpha: 0.45),
    ),
    tooltipTheme: TooltipThemeData(
      decoration: BoxDecoration(color: Palette.ink, borderRadius: BorderRadius.circular(6)),
      textStyle: Typo.small.copyWith(color: Palette.paper),
    ),
  );
}
