package com.osiris.shared.domain.model

import com.osiris.shared.domain.common.Format
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/** `GET /api/v2/me/notifications` item. */
@Serializable
data class NotificationItem(
    val id: Int,
    val kind: String = "system",
    val title: String = "",
    val body: String = "",
    @SerialName("action_route") val actionRoute: String? = null,
    val read: Boolean = false,
    @SerialName("created_at") val createdAt: String = "",
)

/** `GET /api/v2/me/notifications` envelope. */
@Serializable
data class NotificationsData(
    @SerialName("unread_count") val unreadCount: Int = 0,
    val items: List<NotificationItem> = emptyList(),
)

/** `GET /api/v2/challenges/suggested` item for the Circular-Floating Card Deck. */
@Serializable
data class SuggestedChallenge(
    val id: Int,
    val title: String = "",
    val description: String = "",
    @SerialName("course_distance_m") val courseDistanceM: Double = 0.0,
    @SerialName("target_seconds") val targetSeconds: Double = 0.0,
    @SerialName("win_xp") val winXp: Int = 0,
    val participants: Int = 0,
    val joined: Boolean = false,
    @SerialName("is_global") val isGlobal: Boolean = true,
) {
    val distanceLabel: String get() = Format.km(courseDistanceM)
}

/** `GET /api/v2/osirians/suggested` and `/api/v2/osirians/trending` card item. */
@Serializable
data class SuggestedOsirian(
    @SerialName("user_id") val userId: Int,
    val handle: String = "",
    @SerialName("display_name") val displayName: String = "",
    @SerialName("avatar_url") val avatarUrl: String? = null,
    val rank: String = "Bronze",
    val title: String = "Initiate",
    val identity: String = "athlete",
    val xp: Int = 0,
    @SerialName("streak_days") val streakDays: Int = 0,
    @SerialName("domains_claimed") val domainsClaimed: Int = 0,
    @SerialName("verified_workouts") val verifiedWorkouts: Int = 0,
    @SerialName("followers_count") val followersCount: Int = 0,
    val following: Boolean = false,
    @SerialName("trending_reason") val trendingReason: String = "",
) {
    val initials: String
        get() = displayName.trim().split(Regex("\\s+")).filter { it.isNotEmpty() }.take(2)
            .joinToString("") { it.first().uppercaseChar().toString() }.ifEmpty { "OS" }
}

@Serializable
data class FollowStatus(
    @SerialName("user_id") val userId: Int,
    val following: Boolean = false,
    @SerialName("followers_count") val followersCount: Int = 0,
)

@Serializable
data class DismissStatus(
    @SerialName("user_id") val userId: Int,
    val dismissed: Boolean = true,
)

/** Summary metrics attached to a People's Post (`GET /api/v2/feed/posts`). */
@Serializable
data class PostWorkoutSummary(
    @SerialName("exercise_key") val exerciseKey: String? = null,
    @SerialName("exercise_name") val exerciseName: String? = null,
    val sets: Int = 1,
    @SerialName("reps_per_set") val repsPerSet: Int = 0,
    @SerialName("total_reps") val totalReps: Int = 0,
    @SerialName("hold_s") val holdS: Double = 0.0,
    @SerialName("distance_m") val distanceM: Double = 0.0,
    @SerialName("duration_s") val durationS: Double = 0.0,
    @SerialName("domain_area_sqkm") val domainAreaSqkm: Double = 0.0,
    @SerialName("streak_days") val streakDays: Int = 0,
    @SerialName("crystals_earned") val crystalsEarned: Int = 0,
    @SerialName("xp_earned") val xpEarned: Int = 0,
    @SerialName("measure_label") val measureLabel: String? = null,
)

/** Comment on a People's Post (`GET/POST /api/v2/feed/posts/{id}/comments`). */
@Serializable
data class PostCommentItem(
    val id: Int,
    @SerialName("post_id") val postId: Int,
    @SerialName("user_id") val userId: Int,
    @SerialName("author_name") val authorName: String = "",
    @SerialName("author_avatar_url") val authorAvatarUrl: String? = null,
    @SerialName("author_rank") val authorRank: String = "Bronze",
    val body: String = "",
    @SerialName("created_at") val createdAt: String = "",
)

/** One post in People's Posts (`GET /api/v2/feed/posts`). */
@Serializable
data class FeedPost(
    val id: Int,
    @SerialName("user_id") val userId: Int,
    @SerialName("author_name") val authorName: String = "",
    @SerialName("author_handle") val authorHandle: String = "",
    @SerialName("author_avatar_url") val authorAvatarUrl: String? = null,
    @SerialName("author_rank") val authorRank: String = "Bronze",
    @SerialName("author_title") val authorTitle: String = "Initiate",
    val kind: String = "workout",
    val caption: String = "",
    @SerialName("media_url") val mediaUrl: String? = null,
    /** Path of the post's photo on the API host (`/api/v2/social/media/...`), or null. */
    @SerialName("photo_url") val photoUrl: String? = null,
    /** Server-copied stats of the workouts attached to the post. */
    val attachments: List<PostAttachment> = emptyList(),
    val chart: PostChart? = null,
    val summary: PostWorkoutSummary = PostWorkoutSummary(),
    val reactions: Map<String, Int> = emptyMap(),
    @SerialName("total_reactions") val totalReactions: Int = 0,
    @SerialName("my_reaction") val myReaction: String? = null,
    @SerialName("comment_count") val commentCount: Int = 0,
    @SerialName("recent_comments") val recentComments: List<PostCommentItem> = emptyList(),
    @SerialName("share_count") val shareCount: Int = 0,
    @SerialName("created_at") val createdAt: String = "",
) {
    val authorInitials: String
        get() = authorName.trim().split(Regex("\\s+")).filter { it.isNotEmpty() }.take(2)
            .joinToString("") { it.first().uppercaseChar().toString() }.ifEmpty { "OS" }

    val kindBadgeLabel: String
        get() = when (kind) {
            "workout" -> "Camera Verified Workout"
            "run" -> "GPS Verified Run"
            "domain_claim" -> "Domain Acquired"
            "streak" -> "Streak Milestone"
            "crystal_earn" -> "Mana Crystals Earned"
            else -> "Osirian Update"
        }

    fun reactionCount(type: String): Int = reactions[type] ?: 0

    /** When the post was made, or null if the server sent no usable time. */
    val createdInstant: kotlin.time.Instant?
        get() = runCatching { ServerInstantSerializer.parse(createdAt) }.getOrNull()

    /** True when the post carries something to look at besides its caption. */
    val hasMedia: Boolean get() = photoUrl != null || attachments.isNotEmpty() || chart != null
}

@Serializable
data class FeedPostsData(
    val items: List<FeedPost> = emptyList(),
)

/** Payload for `POST /api/v2/feed/posts`. */
@Serializable
data class PostCreateDraft(
    val kind: String = "workout",
    val caption: String = "",
    @SerialName("media_url") val mediaUrl: String? = null,
    @SerialName("exercise_key") val exerciseKey: String? = null,
    val sets: Int = 1,
    @SerialName("reps_per_set") val repsPerSet: Int = 0,
    @SerialName("total_reps") val totalReps: Int = 0,
    @SerialName("hold_s") val holdS: Double = 0.0,
    @SerialName("distance_m") val distanceM: Double = 0.0,
    @SerialName("duration_s") val durationS: Double = 0.0,
    @SerialName("domain_area_sqkm") val domainAreaSqkm: Double = 0.0,
    @SerialName("streak_days") val streakDays: Int = 0,
    @SerialName("crystals_earned") val crystalsEarned: Int = 0,
    @SerialName("xp_earned") val xpEarned: Int = 0,
    @SerialName("related_run_id") val relatedRunId: Int? = null,
    @SerialName("related_exercise_session_id") val relatedExerciseSessionId: Int? = null,
    @SerialName("related_domain_id") val relatedDomainId: Int? = null,
    val visibility: String = "public",
)

/** Response from `POST /api/v2/feed/posts/{id}/share`. */
@Serializable
data class PostShareResult(
    @SerialName("post_id") val postId: Int,
    @SerialName("share_count") val shareCount: Int = 0,
    @SerialName("share_text") val shareText: String = "",
    @SerialName("share_url") val shareUrl: String = "",
)

/** One selectable workout in the Streak Start Customizer. */
data class WorkoutOption(
    val key: String,
    val name: String,
    val category: String,
    val isCameraExercise: Boolean,
    val isHold: Boolean = false,
    val cameraOrientation: String = "side",
)

/**
 * Player's customized Streak Start workout plan (e.g. `Push-ups — 10 × 3`, `Plank — 45s × 3`, or `Run — 3.0 km`).
 */
data class WorkoutPlan(
    val optionKey: String = "pushup",
    val sets: Int = 3,
    val repsPerSet: Int = 10,
    val holdSecondsPerSet: Int = 45,
    val targetDistanceKm: Double = 3.0,
) {
    val option: WorkoutOption
        get() = WORKOUT_OPTIONS.firstOrNull { it.key == optionKey } ?: WORKOUT_OPTIONS.first()

    val measureLabel: String
        get() = when {
            !option.isCameraExercise && optionKey == "domain_claim" ->
                "${option.name} — ${Format.fixed(targetDistanceKm, 1)} km loop"
            !option.isCameraExercise ->
                "${option.name} — ${Format.fixed(targetDistanceKm, 1)} km"
            option.isHold ->
                "${option.name} — ${holdSecondsPerSet}s × $sets"
            else ->
                "${option.name} — $repsPerSet × $sets"
        }

    val badgeLabel: String
        get() = if (option.isCameraExercise) {
            "AI Camera Verified (${if (option.cameraOrientation == "front") "Front" else "Side-on"})"
        } else {
            "GPS Verified"
        }

    companion object {
        val WORKOUT_OPTIONS: List<WorkoutOption> = listOf(
            // GPS activities
            WorkoutOption("run", "Run", "GPS Outdoor", isCameraExercise = false),
            WorkoutOption("walk", "Walk", "GPS Outdoor", isCameraExercise = false),
            WorkoutOption("domain_claim", "Claim Domain", "GPS Territory", isCameraExercise = false),
            // 16 Camera-Verified Bodyweight Exercises
            WorkoutOption("pushup", "Push-ups", "Upper Body", isCameraExercise = true, cameraOrientation = "side"),
            WorkoutOption("squat", "Squats", "Lower Body", isCameraExercise = true, cameraOrientation = "side"),
            WorkoutOption("lunge", "Lunges", "Lower Body", isCameraExercise = true, cameraOrientation = "side"),
            WorkoutOption("situp", "Sit-ups", "Core", isCameraExercise = true, cameraOrientation = "side"),
            WorkoutOption("jumping_jack", "Jumping Jacks", "Cardio", isCameraExercise = true, cameraOrientation = "front"),
            WorkoutOption("high_knees", "High Knees", "Cardio", isCameraExercise = true, cameraOrientation = "side"),
            WorkoutOption("plank", "Plank", "Core Hold", isCameraExercise = true, isHold = true, cameraOrientation = "side"),
            WorkoutOption("glute_bridge", "Glute Bridges", "Lower Body", isCameraExercise = true, cameraOrientation = "side"),
            WorkoutOption("calf_raise", "Calf Raises", "Lower Body", isCameraExercise = true, cameraOrientation = "side"),
            WorkoutOption("shoulder_press", "Pike / Shoulder Press", "Upper Body", isCameraExercise = true, cameraOrientation = "front"),
            WorkoutOption("tricep_dip", "Tricep Dips", "Upper Body", isCameraExercise = true, cameraOrientation = "side"),
            WorkoutOption("mountain_climber", "Mountain Climbers", "Cardio Core", isCameraExercise = true, cameraOrientation = "side"),
            WorkoutOption("leg_raise", "Lying Leg Raises", "Core", isCameraExercise = true, cameraOrientation = "side"),
            WorkoutOption("wall_sit", "Wall Sit", "Lower Hold", isCameraExercise = true, isHold = true, cameraOrientation = "side"),
            WorkoutOption("side_jack", "Star / Side Jacks", "Cardio", isCameraExercise = true, cameraOrientation = "front"),
            WorkoutOption("burpee", "Squat Thrust / Burpees", "Full Body", isCameraExercise = true, cameraOrientation = "side"),
        )
    }
}
