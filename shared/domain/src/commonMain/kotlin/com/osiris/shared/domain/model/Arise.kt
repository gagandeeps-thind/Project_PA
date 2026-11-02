package com.osiris.shared.domain.model

import com.osiris.shared.domain.run.LatLng
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/** A route every player can see and run. [line] is trimmed at both ends when [hideEnds]. */
@Serializable
data class AriseRoute(
    val id: Int,
    val name: String,
    @SerialName("activity_type") val activityType: String,
    @SerialName("distance_m") val distanceM: Double,
    @SerialName("benchmark_seconds") val benchmarkSeconds: Double,
    @SerialName("hide_ends") val hideEnds: Boolean,
    @SerialName("owner_name") val ownerName: String,
    @Serializable(with = RouteSerializer::class) val line: List<LatLng>,
)

/** Base map look on the Arise tab. */
enum class MapStyle(val label: String) { STANDARD("Standard"), SATELLITE("Satellite"), HYBRID("Hybrid"), WINTER("Winter") }

/** Overlays that can be on together. */
enum class Overlay(val label: String) { POIS("POIs"), BIKE_LANES("Bike lanes") }

/** Activity heatmaps; one at a time. */
enum class Heatmap(val wire: String, val label: String) {
    GLOBAL("global", "Global run"),
    WEEKLY("weekly", "Weekly run"),
    NIGHT("night", "Night run"),
    PERSONAL("personal", "Personal"),
}

/** Slope layers drawn from elevation; one at a time. */
enum class TerrainLayer(val label: String) { AVALANCHE("Avalanche gradient"), GRADIENT("Gradient"), ASPECT("Aspect") }
