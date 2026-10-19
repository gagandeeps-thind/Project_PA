package com.osiris.shared.domain.common

import kotlin.math.roundToLong

/** Display formatting shared by both apps, so Android and iOS show identical numbers. */
object Format {
    /** `m:ss`, or `h:mm:ss` from one hour. */
    fun duration(seconds: Double): String {
        val s = seconds.roundToLong().coerceAtLeast(0)
        val h = s / 3600
        val m = (s % 3600) / 60
        val sec = s % 60
        val mm = m.toString().padStart(if (h > 0) 2 else 1, '0')
        val ss = sec.toString().padStart(2, '0')
        return if (h > 0) "$h:$mm:$ss" else "$mm:$ss"
    }

    /** `850 m` or `2.40 km`. */
    fun distance(metres: Double): String =
        if (metres >= 1000) "${fixed(metres / 1000, 2)} km" else "${metres.roundToLong()} m"

    /** `3.2 km`, or whole kilometres from 10 km. */
    fun km(metres: Double): String {
        val km = metres / 1000
        return if (km >= 10) "${fixed(km, 0)} km" else "${fixed(km, 1)} km"
    }

    /** Fixed decimals without platform locale formatting (no `String.format` in common code). */
    fun fixed(value: Double, decimals: Int): String {
        var factor = 1L
        repeat(decimals) { factor *= 10 }
        val negative = value < 0
        val scaled = (kotlin.math.abs(value) * factor).roundToLong()
        val whole = scaled / factor
        val frac = scaled % factor
        val body = if (decimals == 0) "$whole" else "$whole." + frac.toString().padStart(decimals, '0')
        return if (negative && scaled != 0L) "-$body" else body
    }
}
