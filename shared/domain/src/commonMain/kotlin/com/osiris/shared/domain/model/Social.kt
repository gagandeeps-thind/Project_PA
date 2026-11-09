package com.osiris.shared.domain.model

import com.osiris.shared.domain.common.Format
import kotlin.time.Instant
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/** Stats of one workout attached to a post, copied by the server from its own session row. */
@Serializable
data class PostAttachment(
    @SerialName("session_id") val sessionId: Int,
    @SerialName("activity_key") val activityKey: String,
    @SerialName("activity_name") val activityName: String = "",
    @SerialName("activity_kind") val activityKind: String = "sensor",
    @Serializable(with = ServerInstantSerializer::class)
    @SerialName("started_at") val startedAt: Instant,
    @SerialName("duration_s") val durationS: Double = 0.0,
    @SerialName("distance_m") val distanceM: Double = 0.0,
    @SerialName("elevation_gain_m") val elevationGainM: Double = 0.0,
    val reps: Int = 0,
    @SerialName("hr_avg") val hrAvg: Double? = null,
    @SerialName("speed_avg") val speedAvg: Double? = null,
    @SerialName("is_pr") val isPr: Boolean = false,
) {
    /** The stat tiles a post card shows, most telling first. Pace only for distance activities. */
    val tiles: List<StatTile>
        get() = buildList {
            if (distanceM > 0) add(StatTile("Distance", Format.distance(distanceM)))
            add(StatTile("Time", Format.duration(durationS)))
            if (distanceM >= MIN_PACE_DISTANCE_M && durationS > 0) {
                add(StatTile("Pace", Format.duration(durationS / (distanceM / METRES_PER_KM)) + " /km"))
            }
            if (reps > 0) add(StatTile("Reps", "$reps"))
            hrAvg?.let { add(StatTile("Avg HR", "${it.toInt()} bpm")) }
            if (elevationGainM >= 1) add(StatTile("Elevation", "${elevationGainM.toInt()} m"))
        }

    private companion object {
        const val METRES_PER_KM = 1000.0
        const val MIN_PACE_DISTANCE_M = 100.0
    }
}

data class StatTile(val label: String, val value: String)

/** A small chart frozen into a post at posting time. */
@Serializable
data class PostChart(
    val kind: String,
    val title: String = "",
    val unit: String = "",
    val labels: List<String> = emptyList(),
    val values: List<Double> = emptyList(),
) {
    val max: Double get() = values.maxOrNull()?.takeIf { it > 0 } ?: 1.0
}

/** A player as the Social tab shows them in lists, search and threads. */
@Serializable
data class SocialUser(
    @SerialName("user_id") val userId: Int,
    @SerialName("display_name") val displayName: String = "",
    val handle: String = "",
    @SerialName("avatar_url") val avatarUrl: String? = null,
    val rank: String = "Bronze",
    val following: Boolean = false,
    @SerialName("follows_me") val followsMe: Boolean = false,
) {
    val initials: String get() = initialsOf(displayName)
}

/** Someone you follow who trained in the last 24 hours: the feed's stories row. */
@Serializable
data class ActiveFriend(
    @SerialName("user_id") val userId: Int,
    @SerialName("display_name") val displayName: String = "",
    @SerialName("avatar_url") val avatarUrl: String? = null,
    @SerialName("activity_key") val activityKey: String = "",
    @SerialName("activity_name") val activityName: String = "",
    val minutes: Int = 0,
) {
    val initials: String get() = initialsOf(displayName)
}

/** `GET /api/v2/social/feed`. */
@Serializable
data class SocialFeedPage(
    @SerialName("active_today") val activeToday: List<ActiveFriend> = emptyList(),
    val items: List<FeedPost> = emptyList(),
    @SerialName("next_before_id") val nextBeforeId: Int? = null,
)

/** `GET /api/v2/social/discover`. */
@Serializable
data class DiscoverPage(
    val interests: List<String> = emptyList(),
    val items: List<FeedPost> = emptyList(),
)

/** `GET /api/v2/social/users/{id}`. */
@Serializable
data class SocialProfile(
    val user: SocialUser,
    val bio: String? = null,
    val title: String = "",
    @SerialName("posts_count") val postsCount: Int = 0,
    @SerialName("followers_count") val followersCount: Int = 0,
    @SerialName("following_count") val followingCount: Int = 0,
    @SerialName("streak_days") val streakDays: Int = 0,
    @SerialName("week_minutes") val weekMinutes: Int = 0,
    @SerialName("week_sessions") val weekSessions: Int = 0,
    @SerialName("is_me") val isMe: Boolean = false,
    @SerialName("can_message") val canMessage: Boolean = false,
    val posts: List<FeedPost> = emptyList(),
)

/** The composer's request: any mix of photo, past workouts and a chart. */
@Serializable
data class SocialPostDraft(
    val caption: String = "",
    @SerialName("photo_jpeg_base64") val photoJpegBase64: String? = null,
    @SerialName("training_session_ids") val trainingSessionIds: List<Int> = emptyList(),
    val chart: String = CHART_NONE,
    val visibility: String = "public",
) {
    val isEmpty: Boolean
        get() = caption.isBlank() && photoJpegBase64 == null && trainingSessionIds.isEmpty() && chart == CHART_NONE

    companion object {
        const val CHART_NONE = "none"
        const val CHART_WEEKLY = "weekly_progress"
        const val MAX_WORKOUTS = 4
    }
}

@Serializable
data class DirectMessage(
    val id: Int,
    @SerialName("sender_id") val senderId: Int,
    @SerialName("recipient_id") val recipientId: Int,
    val body: String,
    @Serializable(with = ServerInstantSerializer::class)
    @SerialName("created_at") val createdAt: Instant,
    val read: Boolean = false,
    val mine: Boolean = false,
)

@Serializable
data class Conversation(
    val user: SocialUser,
    @SerialName("last_message") val lastMessage: DirectMessage,
    @SerialName("unread_count") val unreadCount: Int = 0,
)

/** `GET /api/v2/social/conversations`. */
@Serializable
data class Inbox(
    @SerialName("unread_total") val unreadTotal: Int = 0,
    val items: List<Conversation> = emptyList(),
)

/** `GET /api/v2/social/conversations/{user_id}/messages`: oldest first. */
@Serializable
data class MessageThread(
    val user: SocialUser,
    @SerialName("can_message") val canMessage: Boolean = false,
    val items: List<DirectMessage> = emptyList(),
)

/** Why a player reports a post, comment or player. */
enum class ContentReportReason(val wire: String, val label: String) {
    HARASSMENT("harassment", "Harassment or hate"),
    SPAM("spam", "Spam or scam"),
    PRIVACY("privacy", "Shares private information"),
    OTHER("other", "Sexual, violent or otherwise harmful"),
}

enum class ReportKind(val wire: String) { POST("post"), COMMENT("comment"), USER("user") }

/** What a report is about: a post, comment or player id. */
data class ReportTarget(val kind: ReportKind, val id: Int)

internal fun initialsOf(name: String): String =
    name.trim().split(Regex("\\s+")).filter { it.isNotEmpty() }.take(2)
        .joinToString("") { it.first().uppercaseChar().toString() }.ifEmpty { "OS" }
