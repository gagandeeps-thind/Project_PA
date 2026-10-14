import 'package:flutter/material.dart';

/// Osiris dark RPG theme constants and ThemeData builder.
class OsirisTheme {
  // ── Color Palette ───────────────────────────────────────────────────
  static const Color background = Color(0xFF121212);
  static const Color surface = Color(0xFF1E1E1E);
  static const Color primary = Color(0xFF9D4EDD);    // Purple crystal
  static const Color secondary = Color(0xFF03DAC6);   // Teal glow
  static const Color error = Color(0xFFCF6679);
  static const Color success = Color(0xFF4CAF50);
  static const Color onBackground = Colors.white;
  static const Color onSurface = Colors.white;
  static const Color onPrimary = Colors.white;

  // ── Stat Colors ─────────────────────────────────────────────────────
  static const Color strColor = Color(0xFFE53935);    // Red
  static const Color agiColor = Color(0xFF43A047);    // Green
  static const Color endColor = Color(0xFF1E88E5);    // Blue
  static const Color conColor = Color(0xFFFDD835);    // Yellow

  /// Build the complete dark Material 3 theme for Osiris.
  static ThemeData get darkTheme {
    final colorScheme = ColorScheme.dark(
      primary: primary,
      secondary: secondary,
      surface: surface,
      error: error,
      onPrimary: onPrimary,
      onSecondary: Colors.black,
      onSurface: onSurface,
      onError: Colors.black,
    );

    return ThemeData(
      useMaterial3: true,
      colorScheme: colorScheme,
      scaffoldBackgroundColor: background,
      fontFamily: 'Roboto',

      // AppBar
      appBarTheme: const AppBarTheme(
        backgroundColor: surface,
        foregroundColor: onSurface,
        elevation: 0,
        centerTitle: true,
      ),

      // Cards
      cardTheme: CardThemeData(
        color: surface,
        elevation: 4,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
        ),
      ),

      // Elevated buttons
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: primary,
          foregroundColor: onPrimary,
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(8),
          ),
          textStyle: const TextStyle(
            fontWeight: FontWeight.bold,
            letterSpacing: 1.2,
          ),
        ),
      ),

      // Input fields
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: surface,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: BorderSide(color: primary.withAlpha(128)),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: BorderSide(color: primary.withAlpha(77)),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: primary, width: 2),
        ),
        labelStyle: TextStyle(color: onSurface.withAlpha(179)),
        hintStyle: TextStyle(color: onSurface.withAlpha(102)),
      ),

      // Snackbar
      // Material 3 paints the unfilled part of a bar in a bright tint, so 0% looked full.
      progressIndicatorTheme: const ProgressIndicatorThemeData(linearTrackColor: Colors.white12),

      snackBarTheme: const SnackBarThemeData(
        backgroundColor: surface,
        contentTextStyle: TextStyle(color: onSurface),
      ),

      // Text
      textTheme: const TextTheme(
        headlineLarge: TextStyle(
          fontSize: 28,
          fontWeight: FontWeight.bold,
          color: onBackground,
          letterSpacing: 2.0,
        ),
        headlineMedium: TextStyle(
          fontSize: 22,
          fontWeight: FontWeight.bold,
          color: onBackground,
        ),
        titleLarge: TextStyle(
          fontSize: 18,
          fontWeight: FontWeight.w600,
          color: onBackground,
        ),
        bodyLarge: TextStyle(fontSize: 16, color: onBackground),
        bodyMedium: TextStyle(fontSize: 14, color: onBackground),
        labelLarge: TextStyle(
          fontSize: 14,
          fontWeight: FontWeight.bold,
          letterSpacing: 1.2,
        ),
      ),
    );
  }
}
