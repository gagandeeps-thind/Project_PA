package com.osiris.shared.domain.model

import kotlin.time.Instant
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class TeamGoal(
    @SerialName("goal_km") val goalKm: Double = 0.0,
    @SerialName("progress_km") val progressKm: Double = 0.0,
    val completed: Boolean = false,
    @SerialName("active_members") val activeMembers: Int = 0,
) {
    val fraction: Double get() = if (goalKm <= 0) 0.0 else (progressKm / goalKm).coerceIn(0.0, 1.0)
}

@Serializable
data class Community(
    val slug: String,
    val name: String,
    val kind: String = "other",
    val description: String? = null,
    @SerialName("brand_color") val brandColor: String? = null,
    val city: String? = null,
    val visibility: String = "public",
    val verified: Boolean = false,
    @SerialName("perk_text") val perkText: String? = null,
    @SerialName("member_count") val memberCount: Int = 0,
    @SerialName("my_role") val myRole: String? = null,
    @SerialName("join_code") val joinCode: String? = null,
    @SerialName("team_goal") val teamGoal: TeamGoal? = null,
) {
    val isMember: Boolean get() = myRole != null
    val kindLabel: String get() = KIND_LABELS[kind] ?: "Community"

    companion object {
        val KIND_LABELS = mapOf(
            "running_club" to "Running club",
            "gym" to "Gym",
            "university" to "University group",
            "trainer" to "Personal trainer",
            "race" to "Race",
            "cafe" to "Cafe",
            "corporate" to "Workplace",
            "other" to "Community",
        )
    }
}

@Serializable
data class LeaderboardRow(
    val rank: Int,
    val name: String,
    val points: Int = 0,
    @SerialName("active_days") val activeDays: Int = 0,
    @SerialName("distance_km") val distanceKm: Double = 0.0,
    @SerialName("is_me") val isMe: Boolean = false,
)

@Serializable
data class Leaderboard(
    val title: String = "",
    val scoring: String = "",
    val rows: List<LeaderboardRow> = emptyList(),
    @SerialName("my_row") val myRow: LeaderboardRow? = null,
    @SerialName("ranked_players") val rankedPlayers: Int = 0,
)

/** A club's standing in a season: the average points of its entered members. */
@Serializable
data class CommunityRank(
    val rank: Int,
    val slug: String = "",
    val name: String,
    @SerialName("average_points") val averagePoints: Int = 0,
    @SerialName("entered_members") val enteredMembers: Int = 0,
    @SerialName("is_mine") val isMine: Boolean = false,
)

/** `GET /api/v2/seasons/{slug}/leaderboard`: players and club standings for one season. */
@Serializable
data class SeasonLeaderboard(
    val players: Leaderboard = Leaderboard(),
    val communities: List<CommunityRank> = emptyList(),
)

@Serializable
data class Season(
    val slug: String,
    val name: String,
    val city: String = "",
    val description: String? = null,
    val status: String = "live",
    val entered: Boolean = false,
    val participants: Int = 0,
    @Serializable(with = ServerInstantSerializer::class)
    @SerialName("ends_at") val endsAt: Instant,
)

@Serializable
data class ReferralSummary(
    @SerialName("referral_code") val code: String,
    val url: String,
    val pending: Int = 0,
    val rewarded: Int = 0,
    val rules: List<String> = emptyList(),
)

@Serializable
data class ShareCard(
    val token: String,
    val url: String,
    val headline: String = "",
    @SerialName("share_text") val shareText: String? = null,
) {
    val text: String get() = shareText ?: url
}

@Serializable
data class InviteLink(@SerialName("share_text") val shareText: String, val url: String? = null)

/** A server acknowledgement with a message for the player (reports, joins). */
@Serializable
data class MessageResponse(val message: String = "Done.")

@Serializable
data class BlockEntry(val id: Int, val name: String)

/** Reasons a player can report a challenge for. */
enum class ReportReason(val wire: String, val label: String) {
    UNSAFE_ROUTE("unsafe_route", "Report unsafe route"),
    CHEATING("cheating", "Report cheating"),
    INAPPROPRIATE_NAME("inappropriate_name", "Report offensive title"),
}
