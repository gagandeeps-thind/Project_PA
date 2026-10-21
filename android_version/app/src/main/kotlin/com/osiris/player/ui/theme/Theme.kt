package com.osiris.player.ui.theme

import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import com.osiris.shared.core.design.FrostMatte

fun Long.color() = Color(this)

/** The active FrostMatte palette; screens read it through [FrostTheme.palette]. */
val LocalFrostPalette = staticCompositionLocalOf { FrostMatte.dark }

object FrostTheme {
    val palette: FrostMatte.Palette
        @Composable get() = LocalFrostPalette.current
}

/**
 * Accent colors shared by every screen, from the dark FrostMatte palette. The app renders dark
 * until every screen reads [FrostTheme.palette]; the light palette is defined and previewable.
 */
object OsirisColors {
    val Background = FrostMatte.dark.background.color()
    val Surface = FrostMatte.dark.glassFallback.color()
    val Primary = FrostMatte.dark.accent.color()
    val Secondary = FrostMatte.dark.accentAlt.color()
    val Error = FrostMatte.dark.danger.color()
    val Success = FrostMatte.dark.success.color()
    val Warning = FrostMatte.dark.warning.color()
    val Gold = FrostMatte.dark.gold.color()
    val Muted = FrostMatte.dark.textSecondary.color()
    val Faint = FrostMatte.dark.textMuted.color()
}

private fun scheme(mode: FrostMatte.Mode) = FrostMatte.palette(mode).let { p ->
    val base = if (mode == FrostMatte.Mode.DARK) darkColorScheme() else lightColorScheme()
    base.copy(
        primary = p.accent.color(),
        onPrimary = p.onAccent.color(),
        secondary = p.accentAlt.color(),
        onSecondary = p.background.color(),
        background = p.background.color(),
        onBackground = p.textPrimary.color(),
        surface = p.glassFallback.color(),
        onSurface = p.textPrimary.color(),
        onSurfaceVariant = p.textSecondary.color(),
        surfaceContainer = p.glassFallback.color(),
        outline = p.glassBorder.color(),
        error = p.danger.color(),
        onError = p.onAccent.color(),
    )
}

private fun style(s: FrostMatte.TextStyle, letterSpacing: Float = 0f) = TextStyle(
    fontSize = s.size.sp,
    lineHeight = s.lineHeight.sp,
    fontWeight = FontWeight(s.weight),
    letterSpacing = letterSpacing.sp,
)

private val type = Typography(
    displaySmall = style(FrostMatte.TextStyle.DISPLAY),
    headlineMedium = style(FrostMatte.TextStyle.DISPLAY, letterSpacing = 1f),
    headlineSmall = style(FrostMatte.TextStyle.TITLE),
    titleLarge = style(FrostMatte.TextStyle.HEADLINE),
    titleMedium = style(FrostMatte.TextStyle.CALLOUT),
    bodyLarge = style(FrostMatte.TextStyle.BODY),
    bodyMedium = style(FrostMatte.TextStyle.CALLOUT),
    bodySmall = style(FrostMatte.TextStyle.CAPTION),
    labelLarge = style(FrostMatte.TextStyle.CALLOUT, letterSpacing = 1f),
    labelMedium = style(FrostMatte.TextStyle.CAPTION),
)

@Composable
fun OsirisTheme(mode: FrostMatte.Mode = FrostMatte.Mode.DARK, content: @Composable () -> Unit) {
    CompositionLocalProvider(LocalFrostPalette provides FrostMatte.palette(mode)) {
        MaterialTheme(colorScheme = scheme(mode), typography = type, content = content)
    }
}

@Composable
fun primaryButtonColors() = ButtonDefaults.buttonColors(containerColor = OsirisColors.Primary, contentColor = Color.White)
