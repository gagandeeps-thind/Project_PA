import 'package:flutter/material.dart';

/// Merchant-branded dark theme with cyberpunk cyan / deep purple accents.
/// Glassmorphism-inspired card styles for a premium business feel.
class MerchantTheme {
  // ── Core Palette ──
  static const Color background = Color(0xFF0B0E14);
  static const Color surface = Color(0xFF141824);
  static const Color surfaceLight = Color(0xFF1C2233);
  static const Color primary = Color(0xFF00F0FF);     // Cyberpunk cyan
  static const Color secondary = Color(0xFF7000FF);   // Deep purple
  static const Color error = Color(0xFFEF4444);
  static const Color success = Color(0xFF10B981);
  static const Color warning = Color(0xFFF59E0B);
  static const Color textPrimary = Color(0xFFE8ECF4);
  static const Color textSecondary = Color(0xFF8B95A8);
  static const Color divider = Color(0xFF2A3144);

  // ── Glassmorphism Card Decoration ──
  static BoxDecoration get glassCard => BoxDecoration(
    color: surface.withAlpha(200),
    borderRadius: BorderRadius.circular(16),
    border: Border.all(color: primary.withAlpha(30), width: 1),
    boxShadow: [
      BoxShadow(
        color: Colors.black.withAlpha(80),
        blurRadius: 24,
        offset: const Offset(0, 8),
      ),
    ],
  );

  /// A more prominent card with a subtle cyan glow.
  static BoxDecoration get glassCardAccent => BoxDecoration(
    color: surface.withAlpha(220),
    borderRadius: BorderRadius.circular(16),
    border: Border.all(color: primary.withAlpha(60), width: 1),
    boxShadow: [
      BoxShadow(
        color: primary.withAlpha(20),
        blurRadius: 32,
        offset: const Offset(0, 4),
      ),
      BoxShadow(
        color: Colors.black.withAlpha(80),
        blurRadius: 24,
        offset: const Offset(0, 8),
      ),
    ],
  );

  // ── ThemeData ──
  static final ThemeData darkTheme = ThemeData(
    brightness: Brightness.dark,
    scaffoldBackgroundColor: background,
    primaryColor: primary,
    colorScheme: const ColorScheme.dark(
      primary: primary,
      secondary: secondary,
      surface: surface,
      error: error,
    ),
    fontFamily: 'Inter',
    textTheme: const TextTheme(
      displayLarge: TextStyle(
        fontSize: 32, fontWeight: FontWeight.w800, color: textPrimary,
        letterSpacing: 2.0,
      ),
      titleLarge: TextStyle(
        fontSize: 22, fontWeight: FontWeight.w700, color: textPrimary,
        letterSpacing: 0.5,
      ),
      titleMedium: TextStyle(
        fontSize: 18, fontWeight: FontWeight.w600, color: textPrimary,
      ),
      bodyLarge: TextStyle(fontSize: 16, color: textPrimary),
      bodyMedium: TextStyle(fontSize: 14, color: textSecondary),
      labelLarge: TextStyle(
        fontSize: 14, fontWeight: FontWeight.w700, color: textPrimary,
        letterSpacing: 1.2,
      ),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: primary,
        foregroundColor: background,
        padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 16),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
        ),
        textStyle: const TextStyle(
          fontSize: 15, fontWeight: FontWeight.w800, letterSpacing: 1.5,
          fontFamily: 'Inter',
        ),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: primary,
        side: const BorderSide(color: primary, width: 1.5),
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
        ),
        textStyle: const TextStyle(
          fontSize: 14, fontWeight: FontWeight.w700, letterSpacing: 1.0,
          fontFamily: 'Inter',
        ),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: surfaceLight,
      contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide(color: divider),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide(color: divider),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: primary, width: 2),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: error, width: 1.5),
      ),
      labelStyle: const TextStyle(color: textSecondary),
      hintStyle: const TextStyle(color: textSecondary),
    ),
    appBarTheme: const AppBarTheme(
      backgroundColor: background,
      elevation: 0,
      centerTitle: true,
      titleTextStyle: TextStyle(
        fontSize: 18, fontWeight: FontWeight.w700, color: textPrimary,
        letterSpacing: 1.5, fontFamily: 'Inter',
      ),
      iconTheme: IconThemeData(color: primary),
    ),
    bottomNavigationBarTheme: const BottomNavigationBarThemeData(
      backgroundColor: surface,
      selectedItemColor: primary,
      unselectedItemColor: textSecondary,
      type: BottomNavigationBarType.fixed,
      elevation: 8,
    ),
    dividerTheme: const DividerThemeData(
      color: divider,
      thickness: 1,
    ),
    floatingActionButtonTheme: const FloatingActionButtonThemeData(
      backgroundColor: primary,
      foregroundColor: background,
    ),
    snackBarTheme: SnackBarThemeData(
      backgroundColor: surfaceLight,
      contentTextStyle: const TextStyle(color: textPrimary, fontFamily: 'Inter'),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      behavior: SnackBarBehavior.floating,
    ),
  );
}
