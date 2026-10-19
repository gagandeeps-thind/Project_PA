package com.osiris.shared.domain.run

import kotlin.math.asin
import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.sqrt

/** A WGS84 coordinate in degrees. */
data class LatLng(val lat: Double, val lng: Double)

object Geo {
    private const val EARTH_RADIUS_M = 6_371_008.8

    /** Great-circle distance in metres (haversine); within 0.5% of the ellipsoid at running distances. */
    fun distanceM(a: LatLng, b: LatLng): Double {
        val dLat = (b.lat - a.lat).toRadians()
        val dLng = (b.lng - a.lng).toRadians()
        val h = sin(dLat / 2) * sin(dLat / 2) + cos(a.lat.toRadians()) * cos(b.lat.toRadians()) * sin(dLng / 2) * sin(dLng / 2)
        return 2 * EARTH_RADIUS_M * asin(sqrt(h.coerceIn(0.0, 1.0)))
    }

    private fun Double.toRadians() = this * kotlin.math.PI / 180
}
