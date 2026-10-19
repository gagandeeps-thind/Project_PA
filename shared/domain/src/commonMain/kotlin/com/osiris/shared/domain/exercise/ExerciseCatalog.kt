package com.osiris.shared.domain.exercise

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement

/** A zone bound on the tracked metric: values [above] or [below] a threshold are inside. */
@Serializable
data class Zone(val above: Double? = null, val below: Double? = null) {
    init {
        require(above != null || below != null) { "a zone needs 'above' or 'below'" }
    }

    fun contains(v: Double): Boolean = (above == null || v > above) && (below == null || v < below)

    val threshold: Double get() = above ?: below!!
}

/**
 * A form rule checked while a rep is in progress:
 * - `angle`: the angle at the middle of three [joints] must stay above [min];
 * - `ankle_spread`: ankle distance in torso lengths (median over the rep's peak frames) must reach [min];
 * - `orientation`: the segment between two [joints] must stay within [maxDeg] of [axis].
 */
@Serializable
data class FormRule(
    val code: String,
    val type: String = TYPE_ANGLE,
    val joints: List<String> = emptyList(),
    val min: Double = 0.0,
    val axis: String = "vertical",
    @SerialName("max_deg") val maxDeg: Double = 90.0,
) {
    companion object {
        const val TYPE_ANGLE = "angle"
        const val TYPE_ANKLE_SPREAD = "ankle_spread"
        const val TYPE_ORIENTATION = "orientation"
    }
}

@Serializable
data class Metric(
    val joints: List<String>,
    val sides: String = SIDES_BEST,
    val type: String = "angle",
) {
    companion object {
        const val SIDES_BEST = "best"
        const val SIDES_MIN = "min"
        const val SIDES_MEAN = "mean"
    }
}

/** One exercise from the server catalog (`GET /api/v2/exercises`, bundled with the apps). */
@Serializable
data class ExerciseSpec(
    val key: String,
    val name: String,
    /** `reps` or `hold`. */
    val kind: String,
    /** `side` or `front`: where the phone should stand. */
    val camera: String,
    val instructions: String = "",
    val metric: Metric,
    val rest: Zone,
    val peak: Zone,
    val form: List<FormRule> = emptyList(),
    @SerialName("min_rep_s") val minRepS: Double,
    @SerialName("max_rep_s") val maxRepS: Double,
    @SerialName("max_reps_per_min") val maxRepsPerMin: Int,
    @SerialName("max_hold_s") val maxHoldS: Double = 0.0,
    /** Slowest pose stream (frames per second) the engine counts this exercise reliably at. */
    @SerialName("min_pose_fps") val minPoseFps: Double = 5.0,
    @SerialName("xp_per_rep") val xpPerRep: Int = 0,
    @SerialName("daily_xp_cap") val dailyXpCap: Int = 0,
) {
    val joints: List<String> get() = metric.joints
    val sides: String get() = metric.sides
    val isHold: Boolean get() = kind == "hold"
}

/** Session-level rules, applied on the device exactly as the server re-check applies them. */
@Serializable
data class SessionRules(
    @SerialName("min_valid_ratio") val minValidRatio: Double,
    @SerialName("replay_min_reps") val replayMinReps: Int,
    @SerialName("replay_max_duration_cv") val replayMaxDurationCv: Double,
    @SerialName("min_hold_s") val minHoldS: Double,
    @SerialName("max_session_s") val maxSessionS: Double,
    @SerialName("hard_reasons") val hardReasons: Set<String>,
)

@Serializable
data class ExerciseCatalog(
    @SerialName("rules_version") val rulesVersion: String,
    @SerialName("min_landmark_likelihood") val minLikelihood: Double,
    @SerialName("session_rules") val sessionRules: SessionRules,
    val exercises: List<ExerciseSpec>,
) {
    fun byKey(key: String): ExerciseSpec? = exercises.firstOrNull { it.key == key }

    companion object {
        private val json = Json { ignoreUnknownKeys = true }

        /** Parses the catalog JSON; throws [kotlinx.serialization.SerializationException] on a bad payload. */
        fun parse(source: String): ExerciseCatalog = json.decodeFromString(serializer(), source)

        fun fromJson(element: JsonElement): ExerciseCatalog = json.decodeFromJsonElement(serializer(), element)
    }
}
