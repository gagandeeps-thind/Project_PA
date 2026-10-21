package com.osiris.shared.core.design

/**
 * FrostMatte design tokens: frosted-glass cards over non-reflective matte backgrounds.
 *
 * The single source for both apps. Colors are ARGB (`0xAARRGGBB`) so Compose reads them with
 * `Color(argb)` and SwiftUI with `Color(argb:)`; lengths are density-independent points.
 */
object FrostMatte {
    enum class Mode { DARK, LIGHT }

    /**
     * @property glassFill card fill over the blurred backdrop
     * @property glassFallback opaque-looking fill where the platform cannot blur (Android < 12)
     * @property glassBorder 1 pt hairline around every glass surface
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
        background = 0xFF0E0F14,
        backgroundAccent = 0xFF2A1A4A,
        backgroundAccentAlt = 0xFF0B3A3A,
        glassFill = 0x14FFFFFF, // rgba(255,255,255,0.08)
        glassFallback = 0xE61A1B22,
        glassBorder = 0x2EFFFFFF, // rgba(255,255,255,0.18)
        shadow = 0x59000000,
        textPrimary = 0xFFF4F4F7,
        textSecondary = 0xB3F4F4F7,
        textMuted = 0x80F4F4F7,
        accent = 0xFF9D4EDD,
        onAccent = 0xFFFFFFFF,
        accentAlt = 0xFF03DAC6,
        success = 0xFF4CAF50,
        warning = 0xFFFFC107,
        danger = 0xFFCF6679,
        gold = 0xFFFDD835,
    )

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
        accent = 0xFF7B2CBF,
        onAccent = 0xFFFFFFFF,
        accentAlt = 0xFF00897B,
        success = 0xFF2E7D32,
        warning = 0xFFB26A00,
        danger = 0xFFB3261E,
        gold = 0xFFB8860B,
    )

    fun palette(mode: Mode): Palette = if (mode == Mode.DARK) dark else light

    /** Backdrop blur radius, the `backdrop-filter: blur(20px)` of the spec. */
    const val BLUR_RADIUS = 20f
    const val BORDER_WIDTH = 1f

    /** Soft diffuse drop shadow under glass surfaces. */
    object Shadow {
        const val RADIUS = 24f
        const val OFFSET_Y = 8f
    }

    /** Matte grain over backgrounds; keeps large areas non-reflective without a gloss gradient. */
    const val GRAIN_ALPHA = 0.035f

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
        DISPLAY(34f, 40f, 700),
        TITLE(22f, 28f, 700),
        HEADLINE(18f, 24f, 600),
        BODY(16f, 22f, 400),
        CALLOUT(14f, 20f, 500),
        CAPTION(12f, 16f, 500),
    }

    /** Minimum touch target (Material and Apple HIG agree on 44-48). */
    const val MIN_TOUCH_TARGET = 48f
}
