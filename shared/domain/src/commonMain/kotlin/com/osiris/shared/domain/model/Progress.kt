package com.osiris.shared.domain.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject

@Serializable
data class Badge(val code: String, val label: String = code)

/** `GET /api/v2/me/progression`. */
@Serializable
data class Progression(
    val xp: Int = 0,
    @SerialName("performance_rank") val performanceRank: String = "Bronze",
    @SerialName("next_rank_xp") val nextRankXp: Int? = null,
    @SerialName("verified_runs") val verifiedRuns: Int = 0,
    val courses: Int = 0,
    @SerialName("challenges_won") val challengesWon: Int = 0,
    val defenses: Int = 0,
    val badges: List<Badge> = emptyList(),
)

@Serializable
data class Quest(
    val key: String,
    val kind: String,
    val title: String,
    val description: String = "",
    @SerialName("target_m") val targetM: Int = 0,
    val xp: Int = 0,
    val optional: Boolean = false,
    @SerialName("progress_m") val progressM: Double = 0.0,
    val completed: Boolean = false,
    val rewarded: Boolean = false,
) {
    val fraction: Double get() = if (targetM <= 0) 0.0 else (progressM / targetM).coerceIn(0.0, 1.0)

    /** Card heading: first quest, recovery day, or an ordinary day. */
    val heading: String
        get() = when (kind) {
            "starter" -> "YOUR FIRST QUEST"
            "recovery" -> "RECOVERY DAY"
            else -> "TODAY'S QUEST"
        }
}

@Serializable
data class WeeklyGoal(
    @SerialName("active_days_target") val activeDaysTarget: Int = 3,
    @SerialName("active_days") val activeDays: Int = 0,
    @SerialName("distance_m") val distanceM: Double = 0.0,
    val xp: Int = 0,
    val completed: Boolean = false,
)

/** A nearby challenge suggested on the home screen. */
@Serializable
data class StarterChallenge(
    val id: Int,
    val title: String = "Nearby challenge",
    @SerialName("course_distance_m") val courseDistanceM: Double = 0.0,
    @SerialName("distance_km") val distanceKm: Double? = null,
)

/** `GET /api/v2/me/today`: the home screen. */
@Serializable
data class TodayData(
    val tagline: String = "",
    @SerialName("display_name") val displayName: String = "",
    val identity: String = "",
    val goal: String = "fitness",
    val xp: Int = 0,
    @SerialName("performance_rank") val performanceRank: String = "",
    val today: Quest,
    val tomorrow: Quest,
    val week: WeeklyGoal,
    @SerialName("streak_weeks") val streakWeeks: Int = 0,
    @SerialName("starter_challenge") val starterChallenge: StarterChallenge? = null,
    @SerialName("safety_note") val safetyNote: String = "",
    @SerialName("needs_location_consent") val needsLocationConsent: Boolean = false,
)

/** `GET /api/v2/rules`: the public scoring and verification rules, shown as-is. */
typealias RulesDocument = JsonObject
