import 'package:flutter/material.dart';

/// PetMind adaptation of the supplied Genesis visual guide.
/// The named Latin fonts are optional; Korean glyphs use platform fallbacks.
abstract final class GenesisTheme {
  static const primary = Color(0xFF6366F1);
  static const primaryHover = Color(0xFF4F46E5);
  // A slight darkening keeps white button labels above 4.5:1 contrast.
  static const primaryButton = Color(0xFF6063ED);
  static const background = Color(0xFFFAFAFA);
  static const surface = Color(0xFFFFFFFF);
  static const ink = Color(0xFF0A0A0A);
  static const secondaryInk = Color(0xFF6B6B6B);
  static const muted = Color(0xFF9C9C9C);
  static const border = Color(0xFFE8E8EC);
  static const success = Color(0xFF10B981);
  static const warning = Color(0xFFF59E0B);
  static const warningInk = Color(0xFF8A5A00);
  static const error = Color(0xFFEF4444);

  static const _fallback = <String>[
    'Noto Sans KR', 'Malgun Gothic', 'Apple SD Gothic Neo', 'sans-serif',
  ];

  static ThemeData get light {
    final base = ThemeData.light(useMaterial3: true);
    final colors = base.colorScheme.copyWith(
      primary: primary,
      onPrimary: surface,
      surface: surface,
      onSurface: ink,
      outline: border,
      error: error,
      onError: surface,
    );
    final body = base.textTheme.apply(
      bodyColor: ink,
      displayColor: ink,
      fontFamily: 'DM Sans',
      fontFamilyFallback: _fallback,
    );
    return base.copyWith(
      colorScheme: colors,
      scaffoldBackgroundColor: background,
      canvasColor: background,
      textTheme: body.copyWith(
        headlineMedium: const TextStyle(
          fontFamily: 'General Sans', fontFamilyFallback: _fallback,
          color: ink, fontSize: 38, fontWeight: FontWeight.w700,
          letterSpacing: -1.2, height: 1.18,
        ),
        titleLarge: const TextStyle(
          fontFamily: 'General Sans', fontFamilyFallback: _fallback,
          color: ink, fontSize: 24, fontWeight: FontWeight.w700,
          letterSpacing: -0.5, height: 1.25,
        ),
        titleMedium: const TextStyle(
          fontFamily: 'General Sans', fontFamilyFallback: _fallback,
          color: ink, fontSize: 18, fontWeight: FontWeight.w700,
        ),
        bodyMedium: const TextStyle(
          fontFamily: 'DM Sans', fontFamilyFallback: _fallback,
          color: ink, fontSize: 15, height: 1.5,
        ),
        bodySmall: const TextStyle(
          fontFamily: 'DM Sans', fontFamilyFallback: _fallback,
          color: secondaryInk, fontSize: 13, height: 1.45,
        ),
        labelLarge: const TextStyle(
          fontFamily: 'DM Sans', fontFamilyFallback: _fallback,
          color: ink, fontSize: 14, fontWeight: FontWeight.w500,
        ),
      ),
      appBarTheme: const AppBarTheme(
        backgroundColor: surface,
        foregroundColor: ink,
        elevation: 0,
        scrolledUnderElevation: 0,
        surfaceTintColor: Colors.transparent,
        toolbarHeight: 56,
        titleTextStyle: TextStyle(
          fontFamily: 'DM Sans', fontFamilyFallback: _fallback,
          color: ink, fontSize: 18, fontWeight: FontWeight.w700,
        ),
        shape: Border(bottom: BorderSide(color: border)),
      ),
      cardTheme: CardThemeData(
        color: surface,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          side: const BorderSide(color: border),
          borderRadius: BorderRadius.circular(12),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: primaryButton,
          foregroundColor: surface,
          minimumSize: const Size(0, 44),
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
          textStyle: const TextStyle(fontFamily: 'DM Sans', fontFamilyFallback: _fallback,
            fontSize: 14, fontWeight: FontWeight.w500),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: ink,
          side: const BorderSide(color: border),
          minimumSize: const Size(0, 44),
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
          textStyle: const TextStyle(fontFamily: 'DM Sans', fontFamilyFallback: _fallback,
            fontSize: 14, fontWeight: FontWeight.w500),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: primaryHover,
          minimumSize: const Size(0, 38),
          textStyle: const TextStyle(fontFamily: 'DM Sans', fontFamilyFallback: _fallback,
            fontSize: 14, fontWeight: FontWeight.w500),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: surface,
        contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        labelStyle: const TextStyle(fontFamily: 'DM Sans', fontFamilyFallback: _fallback,
          color: secondaryInk, fontSize: 14),
        hintStyle: const TextStyle(fontFamily: 'DM Sans', fontFamilyFallback: _fallback,
          color: secondaryInk, fontSize: 14),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(6),
          borderSide: const BorderSide(color: border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(6),
          borderSide: const BorderSide(color: primary, width: 2),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(6),
          borderSide: const BorderSide(color: error),
        ),
      ),
      chipTheme: ChipThemeData(
        backgroundColor: const Color(0xFFF4F4F5),
        side: BorderSide.none,
        shape: const StadiumBorder(),
        labelStyle: const TextStyle(fontFamily: 'DM Sans', fontFamilyFallback: _fallback,
          color: secondaryInk, fontSize: 12),
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      ),
      dividerTheme: const DividerThemeData(color: border, thickness: 1),
      listTileTheme: const ListTileThemeData(
        iconColor: secondaryInk,
        textColor: ink,
        contentPadding: EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      ),
      checkboxTheme: CheckboxThemeData(
        fillColor: WidgetStateProperty.resolveWith(
          (states) => states.contains(WidgetState.selected) ? primary : surface,
        ),
        side: const BorderSide(color: border, width: 2),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(5)),
      ),
      dialogTheme: DialogThemeData(
        backgroundColor: surface,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    );
  }
}
