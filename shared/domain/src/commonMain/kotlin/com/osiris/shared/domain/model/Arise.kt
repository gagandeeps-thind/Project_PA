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

/** One set of an Exceed workout: reps on camera, then a rest. */
@Serializable
data class WorkoutSet(
    @SerialName("exercise_key") val exerciseKey: String,
    val reps: Int,
    @SerialName("rest_s") val restS: Int,
)

@Serializable
data class AriseWorkout(val sets: List<WorkoutSet>, @SerialName("total_reps") val totalReps: Int)

/** A claimed area. Attackers must beat [distanceM] (at least) and [durationS] (less), then [workout] if any. */
@Serializable
data class AriseDomain(
    val id: Int,
    @SerialName("owner_id") val ownerId: Int,
    @SerialName("owner_name") val ownerName: String,
    @SerialName("area_sqkm") val areaSqkm: Double,
    @SerialName("distance_m") val distanceM: Double,
    @SerialName("duration_s") val durationS: Double,
    @SerialName("centroid_lat") val centroidLat: Double,
    @SerialName("centroid_lng") val centroidLng: Double,
    @Serializable(with = RouteSerializer::class) val geometry: List<LatLng> = emptyList(),
    val workout: AriseWorkout? = null,
    @SerialName("photo_url") val photoUrl: String? = null,
    val difficulty: String? = null,
)

@Serializable
data class AriseDomains(val suggested: List<AriseDomain> = emptyList(), val hard: List<AriseDomain> = emptyList())

@Serializable
data class AriseWorkoutResult(val completed: Boolean, val domain: AriseDomain)

/** status: won, needs_workout (do [workout] next) or failed ([reasons]). */
@Serializable
data class AriseAttackResult(
    @SerialName("attack_id") val attackId: Int,
    val status: String,
    val reasons: List<String> = emptyList(),
    val workout: AriseWorkout? = null,
    val domain: AriseDomain,
)

/** One heatmap cell: how many runs crossed it. */
@Serializable
data class HeatCell(val lat: Double, val lng: Double, val w: Int)
