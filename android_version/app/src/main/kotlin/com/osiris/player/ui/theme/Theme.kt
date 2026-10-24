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
import androidx.compose.ui.text.ExperimentalTextApi
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontVariation
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import com.osiris.player.R
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
        outline = p.textMuted.color().copy(alpha = 0.5f),
        outlineVariant = p.textMuted.color().copy(alpha = 0.25f),
        error = p.danger.color(),
        onError = p.onAccent.color(),
        // Material's defaults for these are purple. Selected chips and indicators are controls, so they
        // stay a raised neutral slate; the accent is kept for each screen's focal item and main action.
        primaryContainer = p.accent.color(),
        onPrimaryContainer = p.onAccent.color(),
        secondaryContainer = Color(0xFF353A44),
        onSecondaryContainer = p.textPrimary.color(),
        tertiary = p.accentAlt.color(),
        onTertiary = p.onAccent.color(),
        tertiaryContainer = p.accentAlt.color(),
        onTertiaryContainer = p.onAccent.color(),
        inversePrimary = p.accent.color(),
        surfaceTint = p.background.color(),
        surfaceVariant = p.glassFallback.color(),
        surfaceContainerLowest = p.background.color(),
        surfaceContainerLow = p.glassFallback.color(),
        surfaceContainerHigh = p.glassFallback.color(),
        surfaceContainerHighest = p.glassFallback.color(),
        surfaceBright = p.glassFallback.color(),
        surfaceDim = p.background.color(),
    )
}

/** Both families are variable fonts (res/font, SIL OFL); each weight is one instance of the same file. */
@OptIn(ExperimentalTextApi::class)
private fun variable(res: Int, vararg weights: Int) = FontFamily(
    weights.map { w -> Font(res, FontWeight(w), variationSettings = FontVariation.Settings(FontVariation.weight(w))) },
)

/** Display and body. */
val Manrope = variable(R.font.manrope, 400, 500, 600, 700, 800)

/** Small uppercase labels and figures that should recede (units, ranks, section headers). */
val GeistMono = variable(R.font.geist_mono, 500, 600)

private fun style(s: FrostMatte.TextStyle, letterSpacing: Float = 0f, family: FontFamily = Manrope) = TextStyle(
    fontFamily = family,
    fontSize = s.size.sp,
    lineHeight = s.lineHeight.sp,
    fontWeight = FontWeight(s.weight),
    letterSpacing = letterSpacing.sp,
)

private val type = Typography(
    displayLarge = style(FrostMatte.TextStyle.HERO).copy(letterSpacing = FrostMatte.HERO_TRACKING_EM.em),
    displayMedium = style(FrostMatte.TextStyle.DISPLAY, letterSpacing = -1f).copy(fontWeight = FontWeight.ExtraBold),
    displaySmall = style(FrostMatte.TextStyle.DISPLAY, letterSpacing = -0.8f),
    headlineLarge = style(FrostMatte.TextStyle.DISPLAY, letterSpacing = -0.8f),
    headlineMedium = style(FrostMatte.TextStyle.DISPLAY, letterSpacing = -0.6f),
    headlineSmall = style(FrostMatte.TextStyle.TITLE, letterSpacing = -0.3f),
    titleLarge = style(FrostMatte.TextStyle.HEADLINE),
    titleMedium = style(FrostMatte.TextStyle.CALLOUT).copy(fontWeight = FontWeight.Bold),
    titleSmall = style(FrostMatte.TextStyle.CALLOUT),
    bodyLarge = style(FrostMatte.TextStyle.BODY),
    bodyMedium = style(FrostMatte.TextStyle.CALLOUT),
    bodySmall = style(FrostMatte.TextStyle.CAPTION),
    labelLarge = style(FrostMatte.TextStyle.CALLOUT, letterSpacing = 0.4f).copy(fontWeight = FontWeight.ExtraBold),
    labelMedium = style(FrostMatte.TextStyle.CAPTION, letterSpacing = 0.5f, family = GeistMono).copy(fontWeight = FontWeight.SemiBold),
    labelSmall = style(FrostMatte.TextStyle.CAPTION, letterSpacing = 0.3f, family = GeistMono),
)

@Composable
fun OsirisTheme(mode: FrostMatte.Mode = FrostMatte.Mode.DARK, content: @Composable () -> Unit) {
    CompositionLocalProvider(LocalFrostPalette provides FrostMatte.palette(mode)) {
        MaterialTheme(colorScheme = scheme(mode), typography = type, content = content)
    }
}

@Composable
fun primaryButtonColors() = ButtonDefaults.buttonColors(
    containerColor = OsirisColors.Primary,
    contentColor = FrostMatte.dark.onAccent.color(),
)
