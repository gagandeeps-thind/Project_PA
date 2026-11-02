package com.osiris.shared.domain.model

import kotlin.time.Instant
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/** How an activity is tracked: the camera coach counts reps, GPS runs outdoors, sensors track the rest. */
@Serializable
enum class ActivityKind {
    @SerialName("camera") CAMERA,
    @SerialName("gps") GPS,
    @SerialName("sensor") SENSOR,
}

/** One choice on the Start tab's ribbon and picker. [metric] is what its personal record measures. */
@Serializable
data class TrainingActivity(
    val key: String,
    val name: String,
    val kind: ActivityKind,
    val metric: String,
    @SerialName("max_speed_mps") val maxSpeedMps: Double = 0.0,
    val gps: Boolean = false,
)

/** Train is personal; Challenge sessions also count towards joined group challenges. */
enum class StartMode(val wire: String, val title: String) { TRAIN("train", "Train"), CHALLENGE("challenge", "Challenge") }

/** Telemetry channels as `[[seconds since start, value], ...]`. Speed is m/s. */
@Serializable
data class TrainingSeries(
    val hr: List<List<Double>> = emptyList(),
    val power: List<List<Double>> = emptyList(),
    val speed: List<List<Double>> = emptyList(),
    val elevation: List<List<Double>> = emptyList(),
) {
    val isEmpty: Boolean get() = hr.isEmpty() && power.isEmpty() && speed.isEmpty() && elevation.isEmpty()
}

/** A saved workout. Stats are the server's, computed from [series]. */
@Serializable
data class TrainingSession(
    val id: Int,
    @SerialName("activity_key") val activityKey: String,
    val mode: String,
    val source: String,
    @Serializable(with = ServerInstantSerializer::class)
    @SerialName("started_at") val startedAt: Instant,
    @SerialName("duration_s") val durationS: Double,
    @SerialName("distance_m") val distanceM: Double = 0.0,
    @SerialName("elevation_gain_m") val elevationGainM: Double = 0.0,
    val reps: Int = 0,
    @SerialName("hr_avg") val hrAvg: Double? = null,
    @SerialName("hr_min") val hrMin: Double? = null,
    @SerialName("hr_max") val hrMax: Double? = null,
    @SerialName("power_avg") val powerAvg: Double? = null,
    @SerialName("power_min") val powerMin: Double? = null,
    @SerialName("power_max") val powerMax: Double? = null,
    @SerialName("speed_avg") val speedAvg: Double? = null,
    @SerialName("speed_max") val speedMax: Double? = null,
    @SerialName("elev_min") val elevMin: Double? = null,
    @SerialName("elev_max") val elevMax: Double? = null,
    val posted: Boolean = false,
    @SerialName("is_pr") val isPr: Boolean = false,
    val series: TrainingSeries? = null,
)

/** The upload body; [clientSessionId] makes a retried upload return the same session. */
@Serializable
data class NewTrainingSession(
    @SerialName("client_session_id") val clientSessionId: String,
    @SerialName("activity_key") val activityKey: String,
    val mode: String,
    val source: String,
    @SerialName("started_at") val startedAt: String,
    @SerialName("duration_s") val durationS: Double,
    @SerialName("distance_m") val distanceM: Double = 0.0,
    @SerialName("exercise_session_id") val exerciseSessionId: Int? = null,
    val series: TrainingSeries = TrainingSeries(),
    val devices: List<String> = emptyList(),
)

@Serializable
data class PersonalRecord(val value: Double, val unit: String, @SerialName("session_id") val sessionId: Int)

@Serializable
data class Segments(val workouts: Int = 0, val challenges: Int = 0)

/** Results for one activity: record, segments, totals and the latest session with its series. */
@Serializable
data class TrainingSummary(
    @SerialName("activity_key") val activityKey: String,
    val pr: PersonalRecord? = null,
    val segments: Segments = Segments(),
    @SerialName("total_duration_s") val totalDurationS: Double = 0.0,
    @SerialName("total_distance_m") val totalDistanceM: Double = 0.0,
    @SerialName("total_reps") val totalReps: Int = 0,
    @SerialName("week_sessions") val weekSessions: Int = 0,
    val latest: TrainingSession? = null,
)

@Serializable
data class TrainingSessions(val items: List<TrainingSession> = emptyList())

@Serializable
data class WeeklyProgress(
    @SerialName("week_start") val weekStart: String,
    @SerialName("duration_s") val durationS: Double = 0.0,
    val sessions: Int = 0,
    @SerialName("by_activity") val byActivity: Map<String, Double> = emptyMap(),
)

@Serializable
data class TrainingProgress(val weeks: List<WeeklyProgress> = emptyList())

@Serializable
data class Quote(val id: Int, val text: String, val author: String)

/** Someone you follow or who follows you. */
@Serializable
data class Connection(
    @SerialName("user_id") val userId: Int,
    @SerialName("display_name") val displayName: String,
    @SerialName("avatar_url") val avatarUrl: String? = null,
)

@Serializable
data class GroupMember(
    @SerialName("user_id") val userId: Int,
    @SerialName("display_name") val displayName: String,
    @SerialName("avatar_url") val avatarUrl: String? = null,
    val progress: Double = 0.0,
)

/** A shared goal. [status] is active | ended | cancelled; [myStatus] joined | invited | null. */
@Serializable
data class GroupChallenge(
    val id: Int,
    val title: String,
    @SerialName("activity_key") val activityKey: String,
    val metric: String,
    val target: Double,
    @Serializable(with = ServerInstantSerializer::class)
    @SerialName("starts_at") val startsAt: Instant,
    @Serializable(with = ServerInstantSerializer::class)
    @SerialName("ends_at") val endsAt: Instant,
    @SerialName("is_official") val isOfficial: Boolean = false,
    @SerialName("creator_id") val creatorId: Int? = null,
    val status: String = "active",
    @SerialName("my_status") val myStatus: String? = null,
    @SerialName("my_progress") val myProgress: Double = 0.0,
    val members: Int = 0,
    val top: List<GroupMember> = emptyList(),
    val leaderboard: List<GroupMember> = emptyList(),
) {
    val joined: Boolean get() = myStatus == "joined"
    val active: Boolean get() = status == "active"

    /** 0..1 of the target reached by this player. */
    val myFraction: Double get() = if (target <= 0) 0.0 else (myProgress / target).coerceIn(0.0, 1.0)
}

@Serializable
data class GroupChallenges(
    val official: List<GroupChallenge> = emptyList(),
    val mine: List<GroupChallenge> = emptyList(),
    val invited: List<GroupChallenge> = emptyList(),
    val connections: List<GroupChallenge> = emptyList(),
) {
    /** Everything for the group card, invites first. */
    val group: List<GroupChallenge> get() = invited + mine + connections
}

@Serializable
data class NewGroupChallenge(
    val title: String,
    @SerialName("activity_key") val activityKey: String,
    val metric: String,
    val target: Double,
    val days: Int,
    @SerialName("invitee_ids") val inviteeIds: List<Int> = emptyList(),
)
