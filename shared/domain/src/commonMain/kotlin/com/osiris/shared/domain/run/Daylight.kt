package com.osiris.shared.domain.run

import kotlin.math.PI
import kotlin.math.acos
import kotlin.math.cos
import kotlin.math.sin
import kotlin.time.Instant
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime

/**
 * Sun position for the low-light run warning (Security plan §3: show lighting warnings based on
 * available context). Computed on the phone from the current fix: no network call, and the
 * location never leaves the device. NOAA solar position equations, accurate to about a minute.
 */
object Daylight {
    /** Civil twilight ends when the sun is 6 degrees below the horizon; unlit streets are dark after that. */
    const val DARK_BELOW_DEGREES = -6.0

    /** Solar elevation in degrees at [instant] for [lat], [lng]. */
    fun sunElevation(instant: Instant, lat: Double, lng: Double): Double {
        val t = instant.toLocalDateTime(TimeZone.UTC)
        val dayOfYear = t.dayOfYear
        val hour = t.hour + t.minute / 60.0 + t.second / 3600.0
        // Fractional year in radians.
        val g = 2 * PI / 365 * (dayOfYear - 1 + (hour - 12) / 24)
        val eqTime = 229.18 * (0.000075 + 0.001868 * cos(g) - 0.032077 * sin(g) - 0.014615 * cos(2 * g) - 0.040849 * sin(2 * g))
        val decl = 0.006918 - 0.399912 * cos(g) + 0.070257 * sin(g) - 0.006758 * cos(2 * g) +
            0.000907 * sin(2 * g) - 0.002697 * cos(3 * g) + 0.00148 * sin(3 * g)
        val trueSolarMinutes = hour * 60 + eqTime + 4 * lng
        val hourAngle = (trueSolarMinutes / 4 - 180) * PI / 180
        val latR = lat * PI / 180
        val cosZenith = sin(latR) * sin(decl) + cos(latR) * cos(decl) * cos(hourAngle)
        return 90 - acos(cosZenith.coerceIn(-1.0, 1.0)) * 180 / PI
    }

    /** True when the sun is below civil twilight at [instant] for [lat], [lng]. */
    fun isDark(instant: Instant, lat: Double, lng: Double): Boolean = sunElevation(instant, lat, lng) < DARK_BELOW_DEGREES
}
