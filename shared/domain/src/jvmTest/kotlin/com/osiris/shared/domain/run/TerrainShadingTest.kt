package com.osiris.shared.domain.run

import com.osiris.shared.domain.model.TerrainLayer
import kotlin.math.abs
import kotlin.math.atan
import kotlin.math.tan
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class TerrainShadingTest {
    private val size = 8
    private val metresPerPixel = 10.0

    /** Terrain-RGB pixels for a plane rising [degrees] towards the east (x). */
    private fun eastSlope(degrees: Double): IntArray = IntArray(size * size) { i ->
        val x = i % size
        val elevation = 1000.0 + x * metresPerPixel * tan(Math.toRadians(degrees))
        val v = ((elevation + 10_000) * 10).toInt()
        (0xFF shl 24) or ((v shr 16 and 0xFF) shl 16) or ((v shr 8 and 0xFF) shl 8) or (v and 0xFF)
    }

    @Test
    fun `terrain rgb decodes to metres`() {
        assertEquals(-10_000.0, TerrainShading.elevation(0, 0, 0), 1e-9)
        assertEquals(0.0, TerrainShading.elevation(1, 134, 160), 1e-6)
    }

    @Test
    fun `slope and aspect of a plane rising to the east`() {
        val pixels = eastSlope(30.0)
        val (slope, aspect) = TerrainShading.slopeAspect(pixels, size, 4, 4, metresPerPixel)
        assertTrue(abs(slope - 30.0) < 0.5, "slope $slope")
        // Rising to the east means the face looks west.
        assertTrue(abs(aspect - 270.0) < 1.0, "aspect $aspect")
    }

    @Test
    fun `avalanche bands leave gentle slopes clear and colour steep ones`() {
        assertEquals(0, TerrainShading.color(TerrainLayer.AVALANCHE, 20.0, 0.0) ushr 24)
        val band30 = TerrainShading.color(TerrainLayer.AVALANCHE, 32.0, 0.0)
        val band40 = TerrainShading.color(TerrainLayer.AVALANCHE, 42.0, 0.0)
        assertTrue(band30 ushr 24 > 0 && band40 ushr 24 > 0 && band30 != band40)
    }

    @Test
    fun `aspect is clear on flat ground and the gradient ramp gets warmer with slope`() {
        assertEquals(0, TerrainShading.color(TerrainLayer.ASPECT, 2.0, 90.0) ushr 24)
        assertTrue(TerrainShading.color(TerrainLayer.ASPECT, 20.0, 90.0) != TerrainShading.color(TerrainLayer.ASPECT, 20.0, 270.0))
        val flat = TerrainShading.color(TerrainLayer.GRADIENT, 5.0, 0.0)
        val steep = TerrainShading.color(TerrainLayer.GRADIENT, 40.0, 0.0)
        assertTrue((steep shr 16 and 0xFF) > (flat shr 16 and 0xFF), "steeper is redder")
        assertTrue((flat ushr 24) < (steep ushr 24) / 2, "flat ground stays mostly clear so the map shows through")
    }

    @Test
    fun `shading a tile returns one colour per pixel`() {
        val out = TerrainShading.shade(TerrainLayer.GRADIENT, eastSlope(atan(0.5) * 180 / Math.PI), size, metresPerPixel)
        assertEquals(size * size, out.size)
    }
}
