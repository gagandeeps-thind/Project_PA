package com.osiris.shared.domain.run

import com.osiris.shared.domain.model.TerrainLayer
import kotlin.math.PI
import kotlin.math.atan
import kotlin.math.atan2
import kotlin.math.sqrt

/**
 * Slope layers from Mapbox Terrain-RGB tiles: decode elevation, take the slope and the direction it
 * faces at each pixel, and colour it for the chosen [TerrainLayer]. Pixels are ARGB ints.
 */
object TerrainShading {
    private const val CLEAR = 0
    private const val RGB_BYTE = 0xFF
    private const val RED_SHIFT = 16
    private const val GREEN_SHIFT = 8
    private const val ALPHA_SHIFT = 24
    private const val DEGREES = 180.0 / PI
    private const val FULL_CIRCLE = 360.0
    private const val SECTOR = 45.0
    private const val ASPECT_MIN_SLOPE = 5.0
    private const val GRADIENT_MAX = 45.0
    private const val OVERLAY_ALPHA = 0xB0
    private const val BASE_M = -10_000.0
    private const val STEP_M = 0.1
    private const val RED_STEP = 65_536
    private const val GREEN_STEP = 256

    /** Mapbox Terrain-RGB: height = -10000 + (R * 256 * 256 + G * 256 + B) * 0.1 metres. */
    fun elevation(r: Int, g: Int, b: Int): Double = BASE_M + (r * RED_STEP + g * GREEN_STEP + b) * STEP_M

    private fun elevationAt(pixels: IntArray, size: Int, x: Int, y: Int): Double {
        val p = pixels[y.coerceIn(0, size - 1) * size + x.coerceIn(0, size - 1)]
        return elevation(p shr RED_SHIFT and RGB_BYTE, p shr GREEN_SHIFT and RGB_BYTE, p and RGB_BYTE)
    }

    /** Slope in degrees and aspect (compass direction the slope faces, 0 = north) at pixel (x, y). */
    fun slopeAspect(pixels: IntArray, size: Int, x: Int, y: Int, metresPerPixel: Double): Pair<Double, Double> {
        val dzdx = (elevationAt(pixels, size, x + 1, y) - elevationAt(pixels, size, x - 1, y)) / (2 * metresPerPixel)
        // Image rows run south, so the northward rise is the negative of the row difference.
        val dzdn = (elevationAt(pixels, size, x, y - 1) - elevationAt(pixels, size, x, y + 1)) / (2 * metresPerPixel)
        val slope = atan(sqrt(dzdx * dzdx + dzdn * dzdn)) * DEGREES
        val aspect = (atan2(-dzdx, -dzdn) * DEGREES + FULL_CIRCLE) % FULL_CIRCLE
        return slope to aspect
    }

    /** The overlay colour for one pixel; fully transparent where the layer shows nothing. */
    fun color(layer: TerrainLayer, slope: Double, aspect: Double): Int = when (layer) {
        TerrainLayer.AVALANCHE -> avalanche.lastOrNull { slope >= it.first }?.second ?: CLEAR
        TerrainLayer.GRADIENT -> gradient(slope)
        TerrainLayer.ASPECT -> if (slope < ASPECT_MIN_SLOPE) CLEAR else compass[((aspect + SECTOR / 2) / SECTOR).toInt() % compass.size]
    }

    /** Shades a whole square tile of [size] x [size] Terrain-RGB pixels. */
    fun shade(layer: TerrainLayer, pixels: IntArray, size: Int, metresPerPixel: Double): IntArray = IntArray(size * size) { i ->
        val (slope, aspect) = slopeAspect(pixels, size, i % size, i / size, metresPerPixel)
        color(layer, slope, aspect)
    }

    /** Standard avalanche terrain bands: 27-30, 30-35, 35-40, 40-45, 45+ degrees. */
    private val avalanche = listOf(
        27.0 to argb(0xFFEB3B),
        30.0 to argb(0xFF9800),
        35.0 to argb(0xF44336),
        40.0 to argb(0x9C27B0),
        45.0 to argb(0x212121),
    )

    /** N, NE, E, SE, S, SW, W, NW. */
    private val compass = listOf(0x2196F3, 0x00BCD4, 0x4CAF50, 0xCDDC39, 0xFFC107, 0xFF5722, 0xE91E63, 0x673AB7).map(::argb)

    /** Clear on the flat, through yellow, to red at 45 degrees and steeper. */
    private fun gradient(slope: Double): Int {
        val t = (slope / GRADIENT_MAX).coerceIn(0.0, 1.0)
        val red = (RGB_BYTE * (2 * t).coerceAtMost(1.0)).toInt()
        val green = (RGB_BYTE * (2 * (1 - t)).coerceAtMost(1.0)).toInt()
        // Fades in with steepness so flat ground keeps the map readable.
        val alpha = (OVERLAY_ALPHA * (2 * t).coerceAtMost(1.0)).toInt()
        return (alpha shl ALPHA_SHIFT) or (red shl RED_SHIFT) or (green shl GREEN_SHIFT)
    }

    private fun argb(rgb: Int): Int = (OVERLAY_ALPHA shl ALPHA_SHIFT) or rgb
}
