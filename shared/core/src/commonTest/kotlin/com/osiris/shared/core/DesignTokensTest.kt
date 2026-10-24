package com.osiris.shared.core

import com.osiris.shared.core.design.FrostMatte
import kotlin.math.pow
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/** The Slate palette keeps every text pairing readable: WCAG 2.1 AA, 4.5:1 for body text. */
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
        assertTrue(contrast(p.onAccent, p.accent) >= 7.0, "dark text on the lime accent must stay AAA")
    }

    @Test
    fun theFocalNumberIsTheLargestTypeAndTightlyTracked() {
        val sizes = FrostMatte.TextStyle.entries.map { it.size }
        assertEquals(sizes.max(), FrostMatte.TextStyle.HERO.size)
        assertEquals(72f, FrostMatte.TextStyle.HERO.size)
        assertTrue(FrostMatte.HERO_TRACKING_EM < 0f)
    }
}
