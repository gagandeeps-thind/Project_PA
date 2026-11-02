package com.osiris.player.ui.arise

import android.graphics.BitmapFactory
import com.mapbox.bindgen.DataRef
import com.mapbox.maps.CanonicalTileID
import com.mapbox.maps.CustomRasterSourceClient
import com.mapbox.maps.CustomRasterSourceOptions
import com.mapbox.maps.CustomRasterSourceTileData
import com.mapbox.maps.CustomRasterSourceTileStatus
import com.mapbox.maps.Image
import com.mapbox.maps.MapboxExperimental
import com.mapbox.maps.Style
import com.mapbox.maps.extension.style.layers.addLayer
import com.mapbox.maps.extension.style.layers.generated.rasterLayer
import com.osiris.shared.domain.model.TerrainLayer
import com.osiris.shared.domain.run.TerrainShading
import java.net.URL
import kotlin.math.PI
import kotlin.math.atan
import kotlin.math.cos
import kotlin.math.exp
import kotlin.math.pow
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

private const val SOURCE = "osiris-terrain"
private const val TILE = 256
private const val MIN_ZOOM: Byte = 9
private const val MAX_ZOOM: Byte = 15
private const val OPACITY = 0.75
private const val EARTH_CIRCUMFERENCE_M = 40_075_016.686
private const val CHANNEL = 0xFF
private const val A_SHIFT = 24
private const val R_SHIFT = 16
private const val G_SHIFT = 8
private const val RGBA = 4
private const val HALF = 0.5

/**
 * Gradient, avalanche gradient or aspect drawn on the device: each map tile's Terrain-RGB elevation is
 * fetched from Mapbox and shaded with [TerrainShading] into a custom raster source.
 */
@OptIn(MapboxExperimental::class) // custom raster sources are experimental in Mapbox 11
class TerrainTiles(
    private val style: Style,
    private val token: String,
    private val layer: TerrainLayer,
    private val scope: CoroutineScope,
) {
    fun attach() {
        val callback = CustomRasterSourceClient.valueOf { tile, status ->
            if (status == CustomRasterSourceTileStatus.REQUIRED) fetch(tile)
        }
        style.addStyleCustomRasterSource(
            SOURCE,
            CustomRasterSourceOptions.Builder().clientCallback(callback).tileSize(TILE.toShort())
                .minZoom(MIN_ZOOM).maxZoom(MAX_ZOOM).build(),
        )
        style.addLayer(rasterLayer(LAYER, SOURCE) { rasterOpacity(OPACITY) })
    }

    private fun fetch(tile: CanonicalTileID) {
        scope.launch {
            val image = withContext(Dispatchers.IO) { runCatching { shade(tile) }.getOrNull() } ?: return@launch
            if (style.isValid() && style.styleSourceExists(SOURCE)) {
                style.setStyleCustomRasterSourceTileData(SOURCE, listOf(CustomRasterSourceTileData(tile, image)))
            }
        }
    }

    private fun shade(tile: CanonicalTileID): Image? {
        val url = "https://api.mapbox.com/v4/mapbox.terrain-rgb/${tile.z}/${tile.x}/${tile.y}.pngraw?access_token=$token"
        val bitmap = URL(url).openStream().use { BitmapFactory.decodeStream(it) } ?: return null
        val size = bitmap.width
        val pixels = IntArray(size * size).also { bitmap.getPixels(it, 0, size, 0, 0, size, size) }
        val shaded = TerrainShading.shade(layer, pixels, size, metresPerPixel(tile, size))
        // Mapbox wants premultiplied RGBA bytes.
        val data = DataRef.allocateNative(size * size * RGBA)
        val buffer = data.buffer
        for (argb in shaded) {
            val a = argb ushr A_SHIFT and CHANNEL
            buffer.put((((argb shr R_SHIFT) and CHANNEL) * a / CHANNEL).toByte())
            buffer.put((((argb shr G_SHIFT) and CHANNEL) * a / CHANNEL).toByte())
            buffer.put(((argb and CHANNEL) * a / CHANNEL).toByte())
            buffer.put(a.toByte())
        }
        return Image(size, size, data)
    }

    /** Ground distance of one pixel at the tile's centre latitude. */
    private fun metresPerPixel(tile: CanonicalTileID, size: Int): Double {
        val n = 2.0.pow(tile.z.toInt())
        val lat = atan(sinhOf(PI * (1 - 2 * (tile.y + HALF) / n)))
        return EARTH_CIRCUMFERENCE_M * cos(lat) / (size * n)
    }

    private fun sinhOf(x: Double) = (exp(x) - exp(-x)) / 2

    companion object {
        const val LAYER = "osiris-terrain-layer"

        /** Removes the terrain overlay, if any, so another can replace it. */
        fun detach(style: Style) {
            if (style.styleLayerExists(LAYER)) style.removeStyleLayer(LAYER)
            if (style.styleSourceExists(SOURCE)) style.removeStyleSource(SOURCE)
        }
    }
}
