package com.osiris.player.ui.arise

import androidx.compose.foundation.layout.Box
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.viewinterop.AndroidView
import com.mapbox.bindgen.Value
import com.mapbox.geojson.Point
import com.mapbox.maps.CameraOptions
import com.mapbox.maps.MapView
import com.mapbox.maps.MapboxExperimental
import com.mapbox.maps.Style
import com.mapbox.maps.extension.style.expressions.generated.Expression
import com.mapbox.maps.extension.style.layers.addLayer
import com.mapbox.maps.extension.style.layers.generated.lineLayer
import com.mapbox.maps.extension.style.layers.properties.generated.LineCap
import com.mapbox.maps.extension.style.layers.properties.generated.Visibility
import com.mapbox.maps.extension.style.precipitations.generated.removeSnow
import com.mapbox.maps.extension.style.precipitations.generated.setSnow
import com.mapbox.maps.extension.style.precipitations.generated.snow
import com.mapbox.maps.extension.style.sources.addSource
import com.mapbox.maps.extension.style.sources.generated.rasterDemSource
import com.mapbox.maps.extension.style.sources.generated.vectorSource
import com.mapbox.maps.extension.style.terrain.generated.removeTerrain
import com.mapbox.maps.extension.style.terrain.generated.setTerrain
import com.mapbox.maps.extension.style.terrain.generated.terrain
import com.mapbox.maps.plugin.animation.MapAnimationOptions
import com.mapbox.maps.plugin.animation.easeTo
import com.mapbox.maps.plugin.locationcomponent.createDefault2DPuck
import com.mapbox.maps.plugin.locationcomponent.location
import com.mapbox.maps.plugin.scalebar.scalebar
import com.osiris.player.R
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.domain.model.MapStyle
import com.osiris.shared.domain.model.Overlay
import com.osiris.shared.presentation.arise.AriseState

/**
 * The Arise map (Mapbox): the player's position, the chosen style, POIs, bike lanes and 3D terrain.
 * [recenter] changes whenever the player taps locate-me. Without a token the map is replaced by a note.
 */
@Composable
fun AriseMap(state: AriseState, recenter: Int, modifier: Modifier = Modifier) {
    val context = LocalContext.current
    if (context.getString(R.string.mapbox_access_token).isBlank()) {
        Box(modifier, contentAlignment = Alignment.Center) { Text("Map unavailable in this build", color = OsirisColors.Muted) }
        return
    }
    val map = remember {
        MapView(context).apply {
            scalebar.enabled = false
            location.updateSettings {
                enabled = true
                locationPuck = createDefault2DPuck(withBearing = true)
                puckBearingEnabled = true
                pulsingEnabled = true
            }
        }
    }
    val controller = remember { MapController(map) }
    AndroidView({ map }, modifier)
    SideEffect { controller.show(state) }
    LaunchedEffect(recenter) { if (recenter > 0) controller.recenter() }
}

/** Applies [AriseState] to the map. A style change reloads the style, which drops our layers, so they are re-added. */
private class MapController(private val map: MapView) {
    private var state = AriseState()
    private var loadedStyle: MapStyle? = null
    private var last: Point? = null
    private var centred = false

    init {
        map.location.addOnIndicatorPositionChangedListener { point ->
            last = point
            if (!centred) {
                centred = true
                map.mapboxMap.setCamera(CameraOptions.Builder().center(point).zoom(DEFAULT_ZOOM).build())
            }
        }
    }

    fun show(next: AriseState) {
        val pitchChanged = next.threeD != state.threeD
        state = next
        if (next.style != loadedStyle) {
            loadedStyle = next.style
            map.mapboxMap.loadStyle(styleUri(next.style)) { style -> decorate(style) }
        } else {
            map.mapboxMap.style?.takeIf { it.isStyleLoaded() }?.let(::decorate)
        }
        if (pitchChanged) {
            map.mapboxMap.easeTo(CameraOptions.Builder().pitch(if (next.threeD) PITCH_3D else 0.0).build(), animation)
        }
    }

    fun recenter() {
        val point = last ?: return
        map.mapboxMap.easeTo(CameraOptions.Builder().center(point).zoom(DEFAULT_ZOOM).build(), animation)
    }

    @OptIn(MapboxExperimental::class)
    private fun decorate(style: Style) {
        val s = state
        showPois(style, Overlay.POIS in s.overlays)
        bikeLanes(style, Overlay.BIKE_LANES in s.overlays)
        if (s.threeD) {
            if (!style.styleSourceExists(DEM)) {
                style.addSource(rasterDemSource(DEM) { url("mapbox://mapbox.mapbox-terrain-dem-v1"); tileSize(DEM_TILE) })
            }
            style.setTerrain(terrain(DEM) { exaggeration(TERRAIN_EXAGGERATION) })
        } else {
            style.removeTerrain()
        }
        if (s.style == MapStyle.WINTER) style.setSnow(snow { intensity(SNOW_INTENSITY) }) else style.removeSnow()
    }

    /** Standard styles expose POIs as a config switch; the classic styles as layers named `*poi*`. */
    private fun showPois(style: Style, on: Boolean) {
        if (state.style.isStandard) {
            style.setStyleImportConfigProperty("basemap", "showPointOfInterestLabels", Value.valueOf(on))
        } else {
            style.styleLayers.filter { "poi" in it.id }.forEach {
                style.setStyleLayerProperty(it.id, "visibility", Value.valueOf(if (on) "visible" else "none"))
            }
        }
    }

    private fun bikeLanes(style: Style, on: Boolean) {
        if (!style.styleSourceExists(STREETS)) style.addSource(vectorSource(STREETS) { url("mapbox://mapbox.mapbox-streets-v8") })
        if (!style.styleLayerExists(BIKE_LANES)) {
            val standard = state.style.isStandard
            style.addLayer(
                lineLayer(BIKE_LANES, STREETS) {
                    sourceLayer("road")
                    filter(Expression.fromRaw("""["all",["==",["get","class"],"path"],["==",["get","type"],"cycleway"]]"""))
                    lineColor(BIKE_LANE_COLOR)
                    lineWidth(BIKE_LANE_WIDTH)
                    lineCap(LineCap.ROUND)
                    if (standard) slot("middle")
                },
            )
        }
        style.setStyleLayerProperty(BIKE_LANES, "visibility", Value.valueOf(if (on) Visibility.VISIBLE.value else Visibility.NONE.value))
    }

    private companion object {
        const val DEM = "osiris-dem"
        const val STREETS = "osiris-streets"
        const val BIKE_LANES = "osiris-bike-lanes"
        const val BIKE_LANE_COLOR = "#3DDC97"
        const val BIKE_LANE_WIDTH = 2.5
        const val DEM_TILE = 514L
        const val TERRAIN_EXAGGERATION = 1.2
        const val SNOW_INTENSITY = 0.5
        const val DEFAULT_ZOOM = 15.0
        const val PITCH_3D = 60.0
        val animation = MapAnimationOptions.mapAnimationOptions { duration(600) }
    }
}

private val MapStyle.isStandard get() = this == MapStyle.STANDARD || this == MapStyle.HYBRID

private fun styleUri(style: MapStyle): String = when (style) {
    MapStyle.STANDARD -> Style.STANDARD
    MapStyle.SATELLITE -> Style.SATELLITE
    MapStyle.HYBRID -> Style.STANDARD_SATELLITE
    MapStyle.WINTER -> Style.OUTDOORS
}
