package com.osiris.shared.core.design

/**
 * FrostMatte design tokens, "Slate" edition: glass panes over a charcoal slate backdrop with grain,
 * a specular top rim on every pane, sharp stepped shadows lit from the top left, and one
 * electric accent. Each screen has a single dominant number ([TextStyle.HERO]); everything else
 * recedes into muted neutrals.
 *
 * The single source for both apps. Colors are ARGB (`0xAARRGGBB`) so Compose reads them with
 * `Color(argb)` and SwiftUI with `Color(argb:)`; lengths are density-independent points.
 */
object FrostMatte {
    enum class Mode { DARK, LIGHT }

    /**
     * @property glassFill card fill over the blurred backdrop
     * @property glassFallback opaque-looking fill where the platform cannot blur (Android < 12)
     * @property glassBorder the specular rim: brightest at a pane's top edge, fading to nothing at the bottom
     * @property shadow the hard first step of a pane's shadow (offset down-right from a top-left light)
     */
    data class Palette(
        val background: Long,
        val backgroundAccent: Long,
        val backgroundAccentAlt: Long,
        val glassFill: Long,
        val glassFallback: Long,
        val glassBorder: Long,
        val shadow: Long,
        val textPrimary: Long,
        val textSecondary: Long,
        val textMuted: Long,
        val accent: Long,
        val onAccent: Long,
        val accentAlt: Long,
        val success: Long,
        val warning: Long,
        val danger: Long,
        val gold: Long,
    )

    val dark = Palette(
        background = 0xFF16181D, // charcoal slate, never pure black
        backgroundAccent = 0xFF22262E, // the lit top-left of the backdrop vignette
        backgroundAccentAlt = 0xFF111317, // its shaded bottom-right
        glassFill = 0xD9262A33,
        glassFallback = 0xF2232730,
        glassBorder = 0x80FFFFFF, // rim at the top edge; fades to transparent
        shadow = 0xFF0B0C0F,
        textPrimary = 0xFFF2F3F5,
        textSecondary = 0xFF9DA2AB,
        textMuted = 0xFF8B909A,
        accent = 0xFFC6F432, // electric lime
        onAccent = 0xFF121418,
        accentAlt = 0xFFFF8A4C, // warm orange, streaks and heat only
        success = 0xFF5CE1A6,
        warning = 0xFFFFB547,
        danger = 0xFFFF6B6B,
        gold = 0xFFFFD166,
    )

    /** The pressed-in base under an accent fill: the accent's own shadow, so a lime button reads as a key. */
    const val ACCENT_BASE = 0xFF6E8A12

    val light = Palette(
        background = 0xFFE9EAF0,
        backgroundAccent = 0xFFD9C8F2,
        backgroundAccentAlt = 0xFFC4ECE8,
        glassFill = 0xA6FFFFFF, // rgba(255,255,255,0.65)
        // White hairlines vanish on a light backdrop, so light mode uses a stronger white edge.
        glassBorder = 0x80FFFFFF,
        glassFallback = 0xF2F7F7FA,
        shadow = 0x261A1A2E,
        textPrimary = 0xFF15151C,
        textSecondary = 0xB315151C,
        textMuted = 0x8015151C,
        accent = 0xFF4D7C0F,
        onAccent = 0xFFFFFFFF,
        accentAlt = 0xFFC2410C,
        success = 0xFF2E7D32,
        warning = 0xFFB26A00,
        danger = 0xFFB3261E,
        gold = 0xFFB8860B,
    )

    fun palette(mode: Mode): Palette = if (mode == Mode.DARK) dark else light

    /** Backdrop blur radius, the `backdrop-filter: blur(20px)` of the spec. */
    const val BLUR_RADIUS = 20f
    const val BORDER_WIDTH = 1f

    /**
     * Tactile shadow: two hard steps offset down-right (light from the top left) plus one tight
     * blur for contact, instead of a single soft, muddy drop shadow.
     */
    object Shadow {
        const val STEP1 = 2f
        const val STEP2_X = 5f
        const val STEP2_Y = 6f
        const val STEP2_ALPHA = 0.55f
        const val RADIUS = 12f
        const val OFFSET_Y = 8f
    }

    /** Grain over the backdrop and inside glass, so large areas read as material, not flat fill. */
    const val GRAIN_ALPHA = 0.07f

    object Radius {
        const val SMALL = 12f
        const val MEDIUM = 20f
        const val LARGE = 28f
        const val PILL = 999f
    }

    object Spacing {
        const val XS = 4f
        const val S = 8f
        const val M = 12f
        const val L = 16f
        const val XL = 24f
        const val XXL = 32f
    }

    /** Type scale in points: size to line height. */
    enum class TextStyle(val size: Float, val lineHeight: Float, val weight: Int) {
        /** The one focal number per screen. Set with tight tracking ([HERO_TRACKING_EM]). */
        HERO(72f, 68f, 800),
        DISPLAY(34f, 40f, 700),
        TITLE(22f, 28f, 700),
        HEADLINE(18f, 24f, 600),
        BODY(16f, 22f, 400),
        CALLOUT(14f, 20f, 500),
        CAPTION(12f, 16f, 500),
    }

    /** Letter spacing of [TextStyle.HERO], in em: big numerals need it tight. */
    const val HERO_TRACKING_EM = -0.045f

    /** Minimum touch target (Material and Apple HIG agree on 44-48). */
    const val MIN_TOUCH_TARGET = 48f
}
