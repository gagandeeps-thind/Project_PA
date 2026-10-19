package com.osiris.shared.domain.run

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlin.time.Instant

class DaylightTest {
    private val halifax = 44.65 to -63.58
    private val tromso = 69.65 to 18.96

    private fun at(iso: String) = Instant.parse(iso)
    private fun elev(iso: String, p: Pair<Double, Double>) = Daylight.sunElevation(at(iso), p.first, p.second)
    private fun dark(iso: String, p: Pair<Double, Double>) = Daylight.isDark(at(iso), p.first, p.second)

    @Test
    fun solarNoonElevationMatchesLatitudeAndSolsticeTilt() {
        assertEquals(68.8, elev("2026-06-21T16:15:00Z", halifax), 1.0)
        assertEquals(21.9, elev("2026-12-21T16:15:00Z", halifax), 1.0)
        assertTrue(Daylight.sunElevation(at("2026-03-20T12:07:00Z"), 0.0, 0.0) > 88)
    }

    @Test
    fun matchesAPublishedSunrise() {
        // Halifax, 14 Oct 2026, 07:22 ADT; at official sunrise the sun's centre is 0.833° below the horizon.
        assertEquals(-0.83, elev("2026-10-14T10:22:00Z", halifax), 1.0)
    }

    @Test
    fun nightAndDayInHalifax() {
        assertTrue(dark("2026-06-21T05:00:00Z", halifax))
        assertTrue(dark("2026-12-21T22:00:00Z", halifax))
        assertFalse(dark("2026-12-21T16:00:00Z", halifax))
        assertFalse(dark("2026-06-21T23:00:00Z", halifax))
    }

    @Test
    fun polarDayAndPolarNight() {
        assertTrue(elev("2026-06-21T22:45:00Z", tromso) > 0)
        assertFalse(dark("2026-06-21T22:45:00Z", tromso))
        assertTrue(elev("2026-12-21T10:45:00Z", tromso) < 0)
        assertTrue(dark("2026-12-21T14:00:00Z", tromso))
    }
}
