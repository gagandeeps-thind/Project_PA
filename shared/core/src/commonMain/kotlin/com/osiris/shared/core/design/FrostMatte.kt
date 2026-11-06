package com.osiris.shared.core.design

/**
 * FrostMatte design tokens, "Liquid aqua" edition: inflated panes of aqua glass floating over a
 * pitch-black floor, each with an icy rim that catches one light fixed in the world. Tilting the phone
 * moves each pane's glow and the bright edge of its rim ([Depth.fall]). On black a dark shadow vanishes,
 * so a pane casts teal light instead, like tinted glass throwing colour onto the floor.
 * Aqua and white carry the interface. [Palette.energy] is the hint of orange: a screen's one big action,
 * a streak and the leading edge of live progress, never a fill or a body-text colour.
 * One dominant number per screen ([TextStyle.HERO]).
 *
 * The single source for both apps. Colors are ARGB (`0xAARRGGBB`) so Compose reads them with
 * `Color(argb)` and SwiftUI with `Color(argb:)`; lengths are density-independent points.
 */
object FrostMatte {
    enum class Mode { DARK, LIGHT }

    /**
     * @property glassFill a pane's fill at its bottom edge, over the blurred backdrop
     * @property glassSheen the same fill at its top edge, where the pane catches more light
     * @property glassFallback opaque fill where the platform cannot blur (Android < 12)
     * @property glassBorder the specular rim, brightest on the edge that faces the light
     * @property shadow the colour every pane casts onto the floor
     * @property energy the hint of orange; see the type's notes for where it is allowed
     */
    data class Palette(
        val background: Long,
        val backgroundAccent: Long,
        val backgroundAccentAlt: Long,
        val glassFill: Long,
        val glassSheen: Long,
        val glassFallback: Long,
        val glassBorder: Long,
        val shadow: Long,
        val textPrimary: Long,
        val textSecondary: Long,
        val textMuted: Long,
        val accent: Long,
        val onAccent: Long,
        val accentAlt: Long,
        val energy: Long,
        val onEnergy: Long,
        val success: Long,
        val warning: Long,
        val danger: Long,
        val gold: Long,
    )

    val dark = Palette(
        background = 0xFF000000, // pitch black: the panes float on nothing
        backgroundAccent = 0xFF000000,
        backgroundAccentAlt = 0xFF000000,
        glassFill = 0x14A1F7F5, // aqua glass at its bottom edge
        glassSheen = 0x2EA1F7F5, // and at its top, where it catches more light
        glassFallback = 0xFF0C1A1A,
        glassBorder = 0xE6DFFFFE, // icy rim
        shadow = 0xFF1B7F7D, // teal light thrown onto the floor
        textPrimary = 0xFFFFFFFF,
        textSecondary = 0xFFC7D6D5,
        textMuted = 0xFFA3B8B7,
        accent = 0xFFA1F7F5, // liquid aqua
        onAccent = 0xFF03211F, // deep teal ink: white on aqua is unreadable
        accentAlt = 0xFF6FE3E0, // aqua with more body, for icons and labels beside the accent
        energy = 0xFFF45B0D, // the burst of orange
        onEnergy = 0xFF1A0D06, // ink on orange: dark, because white on this orange fails AA
        success = 0xFF6CC3A0, // verdigris
        warning = 0xFFF2A33A, // amber
        danger = 0xFFFF4A4A, // boiler red
        gold = 0xFFD9A54A, // brass, for crystals and podiums
    )

    /** The lit top and shaded underside of an inflated aqua key, and of an inflated orange key. */
    const val ACCENT_TOP = 0xFFE6FFFE
    const val ACCENT_BASE = 0xFF4FC2BF
    const val ENERGY_TOP = 0xFFFF9257
    const val ENERGY_BASE = 0xFFD14B08

    /** The floor of a neumorphic recess pressed into the glass. */
    const val WELL = 0xFF030909

    val light = Palette(
        background = 0xFFE9EAEE,
        backgroundAccent = 0xFFF6F4F0,
        backgroundAccentAlt = 0xFFD9DCE3,
        glassFill = 0xA6FFFFFF,
        glassSheen = 0xD9FFFFFF,
        glassFallback = 0xF2F7F7FA,
        glassBorder = 0xCCFFFFFF,
        shadow = 0x4D1A1D26,
        textPrimary = 0xFF15171C,
        textSecondary = 0xB315171C,
        textMuted = 0x8C15171C,
        accent = 0xFF0B6E6C,
        onAccent = 0xFFFFFFFF,
        accentAlt = 0xFF0E5F5D,
        energy = 0xFFB23F00,
        onEnergy = 0xFFFFFFFF,
        success = 0xFF3E7B44,
        warning = 0xFFB26A00,
        danger = 0xFFB3261E,
        gold = 0xFF946C12,
    )

    fun palette(mode: Mode): Palette = if (mode == Mode.DARK) dark else light

    /** Backdrop blur radius, the `backdrop-blur-2xl` (40 px) of the spec. */
    const val BLUR_RADIUS = 40f
    const val BORDER_WIDTH = 1f

    /** Grain over the backdrop and inside glass, so large areas read as material, not flat fill. */
    const val GRAIN_ALPHA = 0.05f

    /** Where a shadow falls, as a direction on screen: x to the right, y down, each in -1..1. */
    data class Fall(val x: Float, val y: Float)

    /**
     * Elevation. Every pane sits at a height above the floor; its shadow falls [Fall] times its
     * height, so higher panes cast longer, softer shadows and everything shares one light.
     */
    object Depth {
        /** Height of a card, of floating chrome (tab bar, HUD pills) and of a key's base, in points. */
        const val CARD = 10f
        const val FLOAT = 18f
        const val KEY = 4f

        /** The soft ambient glow's blur, per point of height, and its strength. */
        const val AMBIENT_BLUR_PER_HEIGHT = 2.6f
        const val AMBIENT_ALPHA = 0.45f

        /** The tight contact shadow right under the edge: a short offset and a small blur. */
        const val CONTACT_SHARE = 0.2f
        const val CONTACT_BLUR = 3f
        const val CONTACT_ALPHA = 0.35f

        /** A pressed key shrinks to this and sinks onto its base. */
        const val PRESS_SCALE = 0.95f

        /** The light at rest: up and slightly left, as a phone is usually held. */
        val REST = Fall(0.25f, 0.8f)

        private const val GAIN_X = 0.6f
        private const val GAIN_Y = 0.65f
        private const val FLOOR_Y = 0.35f

        /**
         * The shadow direction for the phone's pose. [downX] and [downY] are world-down projected
         * onto the screen and divided by g (x right, y down): `(0, 1)` held upright, `(0, 0)` flat on a
         * table. Held flat the shadow still falls a little downward, so depth never vanishes.
         */
        fun fall(downX: Float, downY: Float): Fall = Fall(
            (REST.x + GAIN_X * downX).coerceIn(-1f, 1f),
            (FLOOR_Y + GAIN_Y * downY).coerceIn(-1f, 1f),
        )
    }

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

    /** Type scale in points: size to line height. All Manrope and tabular. */
    enum class TextStyle(val size: Float, val lineHeight: Float, val weight: Int) {
        /** The one focal number per screen. Set with tight tracking ([HERO_TRACKING_EM]). */
        HERO(72f, 68f, 800),
        DISPLAY(34f, 40f, 700),
        TITLE(22f, 28f, 700),
        HEADLINE(18f, 24f, 600),
        BODY(16f, 22f, 400),
        CALLOUT(14f, 20f, 500),
        CAPTION(12f, 16f, 600),
    }

    /** Letter spacing of [TextStyle.HERO], in em: big numerals need it tight. */
    const val HERO_TRACKING_EM = -0.045f

    /** Minimum touch target (Material and Apple HIG agree on 44-48). */
    const val MIN_TOUCH_TARGET = 48f
}
