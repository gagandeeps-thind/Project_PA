package com.osiris.shared.core

import com.osiris.shared.core.design.FrostMatte
import kotlin.math.pow
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/** The palette keeps every text pairing readable: WCAG 2.1 AA, 4.5:1 for body text. */
class DesignTokensTest {
    private fun luminance(argb: Long): Double {
        fun channel(shift: Int): Double {
            val c = ((argb shr shift) and 0xFF) / 255.0
            return if (c <= 0.03928) c / 12.92 else ((c + 0.055) / 1.055).pow(2.4)
        }
        return 0.2126 * channel(16) + 0.7152 * channel(8) + 0.0722 * channel(0)
    }

    /** [over] seen through the translucent [glass], as a pane draws it. */
    private fun through(glass: Long, over: Long): Long {
        val a = (glass ushr 24) / 255.0
        fun channel(shift: Int) = (((glass shr shift) and 0xFF) * a + ((over shr shift) and 0xFF) * (1 - a)).toLong() shl shift
        return 0xFF000000 or channel(16) or channel(8) or channel(0)
    }

    private fun contrast(a: Long, b: Long): Double {
        val (hi, lo) = listOf(luminance(a), luminance(b)).sortedDescending()
        return (hi + 0.05) / (lo + 0.05)
    }

    @Test
    fun darkPaletteTextMeetsAaOnTheBackdropAndOnGlass() {
        val p = FrostMatte.dark
        val brightestGlass = through(p.glassSheen, p.glassFallback)
        for (surface in listOf(p.background, p.glassFallback, brightestGlass)) {
            for (text in listOf(p.textPrimary, p.textSecondary, p.textMuted, p.accentAlt)) {
                val ratio = contrast(text, surface)
                assertTrue(ratio >= 4.5, "text ${text.toString(16)} on ${surface.toString(16)} is only $ratio:1")
            }
        }
        assertTrue(contrast(p.onAccent, p.accent) >= 4.5, "ink on the orange accent must stay AA")
        assertTrue(contrast(p.onEnergy, p.energy) >= 4.5, "ink on orange must stay AA")
        assertTrue(contrast(p.accent, p.background) >= 4.5, "orange used as text on the floor must stay AA")
        assertTrue(contrast(p.energy, p.background) >= 4.5, "orange used as an icon on the floor must stay AA")
        assertTrue(contrast(p.danger, p.glassFallback) >= 4.5, "boiler red used as text on a card must stay AA")
        assertTrue(contrast(p.accent, p.glassFallback) >= 4.5, "orange used as text on a card must stay AA")
    }

    @Test
    fun theBrandColoursAreExactlyTheOnesChosen() {
        val p = FrostMatte.dark
        assertEquals(0xFFFF5500, p.accent)
        assertEquals(0xFF95B8C0, p.accentAlt)
        assertEquals(0xFFFFFFFF, p.textPrimary)
        assertEquals(0xFF8E95A2, p.textSecondary)
        assertEquals(0xFF23262B, p.glassFallback)
        assertEquals(0xFF2F343B, p.glassBorder)
    }

    @Test
    fun theFloorIsMatteCharcoal() {
        val p = FrostMatte.dark
        assertEquals(0xFF161719, p.background)
        assertEquals(0xFF1E2024, p.backgroundAccentAlt)
    }

    @Test
    fun shadowsFallDownTheScreenAndSwingWithTheTilt() {
        val upright = FrostMatte.Depth.fall(0f, 1f)
        val flat = FrostMatte.Depth.fall(0f, 0f)
        assertTrue(upright.y > flat.y, "an upright phone throws longer shadows than one lying flat")
        assertTrue(flat.y > 0f, "depth never vanishes, even flat on a table")
        val left = FrostMatte.Depth.fall(-1f, 0.7f)
        val right = FrostMatte.Depth.fall(1f, 0.7f)
        assertTrue(left.x < FrostMatte.Depth.REST.x && right.x > FrostMatte.Depth.REST.x)
        val extreme = FrostMatte.Depth.fall(5f, 5f)
        assertEquals(1f, extreme.x)
        assertEquals(1f, extreme.y)
    }

    @Test
    fun theFocalNumberIsTheLargestTypeAndTightlyTracked() {
        val sizes = FrostMatte.TextStyle.entries.map { it.size }
        assertEquals(sizes.max(), FrostMatte.TextStyle.HERO.size)
        assertEquals(72f, FrostMatte.TextStyle.HERO.size)
        assertTrue(FrostMatte.HERO_TRACKING_EM < 0f)
    }
}
