package com.osiris.shared.core

import com.osiris.shared.core.design.FrostMatte
import kotlin.math.pow
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/** The Boiler glass palette keeps every text pairing readable: WCAG 2.1 AA, 4.5:1 for body text. */
class DesignTokensTest {
    private fun luminance(argb: Long): Double {
        fun channel(shift: Int): Double {
            val c = ((argb shr shift) and 0xFF) / 255.0
            return if (c <= 0.03928) c / 12.92 else ((c + 0.055) / 1.055).pow(2.4)
        }
        return 0.2126 * channel(16) + 0.7152 * channel(8) + 0.0722 * channel(0)
    }

    private fun contrast(a: Long, b: Long): Double {
        val (hi, lo) = listOf(luminance(a), luminance(b)).sortedDescending()
        return (hi + 0.05) / (lo + 0.05)
    }

    @Test
    fun darkPaletteTextMeetsAaOnTheBackdropAndOnGlass() {
        val p = FrostMatte.dark
        for (surface in listOf(p.background, p.glassFallback)) {
            for (text in listOf(p.textPrimary, p.textSecondary, p.textMuted, p.accentAlt)) {
                val ratio = contrast(text, surface)
                assertTrue(ratio >= 4.5, "text ${text.toString(16)} on ${surface.toString(16)} is only $ratio:1")
            }
        }
        // No ink reaches AAA on safety orange (black tops out near 5.7:1), so key labels hold AA.
        assertTrue(contrast(p.onAccent, p.accent) >= 4.5, "ink on the ember accent must stay AA")
        assertTrue(contrast(p.accent, p.background) >= 4.5, "deep orange used as text on black must stay AA")
        assertTrue(contrast(p.danger, p.glassFallback) >= 4.5, "boiler red used as text on glass must stay AA")
    }

    @Test
    fun theFloorIsPitchBlack() {
        val p = FrostMatte.dark
        assertEquals(listOf(0xFF000000, 0xFF000000, 0xFF000000), listOf(p.background, p.backgroundAccent, p.backgroundAccentAlt))
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
