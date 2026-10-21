package com.osiris.shared.domain.model

import com.osiris.shared.domain.common.Format
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/** The Discover tab's sections, in screen order. */
enum class HubSection(val wire: String, val title: String, val empty: String) {
    LIVE("live", "Happening now", "Nothing running right now. Create one and invite a friend."),
    UPCOMING("upcoming", "Upcoming", "No challenges scheduled yet."),
    COMMUNITY("community", "From your communities", "Join a community to see its challenges here."),
    FINISHED("finished", "Just finished", "No results in the last two weeks."),
}

/** A podium place on a finished challenge; names follow the leaderboard opt-in (ADR-004). */
@Serializable
data class Finisher(
    val rank: Int,
    val name: String,
    @SerialName("elapsed_seconds") val elapsedSeconds: Double,
)

/** A challenge card on Discover, with the extra the section needs. */
@Serializable
data class HubChallenge(
    val challenge: ChallengeSummary,
    val participants: Int = 0,
    @SerialName("starts_in_seconds") val startsInSeconds: Int? = null,
    @SerialName("community_name") val communityName: String? = null,
    val winners: List<Finisher> = emptyList(),
    @SerialName("xp_paid") val xpPaid: Int? = null,
)

/** `GET /api/v2/challenge-hub`. */
@Serializable
data class HubSectionData(val section: String, val items: List<HubChallenge> = emptyList())

/** The global boards on Social. Rewards ranks platform XP and badges, never money (ADR-005). */
enum class BoardKind(val wire: String, val title: String) {
    DISTANCE("distance", "Distance"),
    PACE("pace", "Pace Index"),
    REPS("reps", "Reps"),
    REWARDS("rewards", "Rewards"),
}

enum class BoardPeriod(val wire: String, val title: String) {
    WEEK("week", "This week"),
    ALL("all", "All time"),
}

enum class BoardExercise(val wire: String, val title: String) {
    PUSHUP("pushup", "Push-ups"),
    SQUAT("squat", "Squats"),
    PULLUP("pullup", "Pull-ups"),
    PLANK("plank", "Plank"),
}

@Serializable
data class BoardRow(
    val rank: Int,
    val name: String,
    val value: Double,
    @SerialName("is_me") val isMe: Boolean = false,
)

/** `GET /api/v2/leaderboards/global`. */
@Serializable
data class GlobalBoard(
    val board: String,
    val period: String,
    val exercise: String? = null,
    val unit: String,
    @SerialName("lower_is_better") val lowerIsBetter: Boolean = false,
    val explainer: String = "",
    val rows: List<BoardRow> = emptyList(),
    @SerialName("my_row") val myRow: BoardRow? = null,
    @SerialName("ranked_players") val rankedPlayers: Int = 0,
) {
    /** `12.4 km`, `21:30` (time units), `120 reps` or `350 XP`. */
    fun format(value: Double): String = when (unit) {
        "km" -> "${Format.fixed(value, 1)} km"
        "s" -> Format.duration(value)
        "xp" -> "${Format.fixed(value, 0)} XP"
        else -> "${Format.fixed(value, 0)} $unit"
    }
}
