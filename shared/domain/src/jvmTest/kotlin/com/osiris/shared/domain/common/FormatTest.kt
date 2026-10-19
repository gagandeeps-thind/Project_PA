package com.osiris.shared.domain.common

import com.osiris.shared.domain.run.Geo
import com.osiris.shared.domain.run.LatLng
import kotlin.test.Test
import kotlin.test.assertEquals

class FormatTest {
    @Test
    fun durations() {
        assertEquals("0:00", Format.duration(0.0))
        assertEquals("4:05", Format.duration(245.0))
        assertEquals("1:02:03", Format.duration(3723.0))
    }

    @Test
    fun distances() {
        assertEquals("850 m", Format.distance(850.0))
        assertEquals("2.40 km", Format.distance(2400.0))
        assertEquals("3.2 km", Format.km(3240.0))
        assertEquals("12 km", Format.km(12400.0))
        assertEquals("-1.5", Format.fixed(-1.5, 1))
        assertEquals("0.07", Format.fixed(0.066, 2))
    }

    @Test
    fun haversineDistance() {
        // One degree of latitude is ~111.2 km.
        assertEquals(111_195.0, Geo.distanceM(LatLng(0.0, 0.0), LatLng(1.0, 0.0)), 50.0)
        assertEquals(0.0, Geo.distanceM(LatLng(44.6, -63.5), LatLng(44.6, -63.5)))
    }
}
