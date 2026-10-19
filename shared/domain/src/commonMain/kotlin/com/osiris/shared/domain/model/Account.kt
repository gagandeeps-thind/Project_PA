package com.osiris.shared.domain.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/** A signed-in session: the bearer token and whose it is. */
data class Session(val token: String, val userId: Int)

/** `POST /api/v1/auth/login`. */
@Serializable
data class LoginResponse(
    @SerialName("access_token") val accessToken: String,
    val role: String,
    @SerialName("id") val userId: Int,
)

/** `POST /api/v2/auth/register`. */
@Serializable
data class RegisterResponse(
    @SerialName("access_token") val accessToken: String,
    val profile: PlayerProfile,
)

/** `POST /api/v2/me/sessions/revoke`: every other device is signed out; this one gets a fresh token. */
@Serializable
data class TokenResponse(@SerialName("access_token") val accessToken: String)

/**
 * The legacy v1 user record (`GET /api/v1/users/{id}`). It carries no role: the player-only
 * rule is enforced at sign-in, the only place a token is stored.
 */
@Serializable
data class UserProfile(
    val id: Int,
    val email: String = "",
    val xp: Int = 0,
    val rank: String = "Unranked",
    val title: String = "Novice",
    val streak: Int = 0,
    @SerialName("mana_crystals") val manaCrystals: Int = 0,
    @SerialName("str_stat") val strStat: Int = 0,
    @SerialName("agi_stat") val agiStat: Int = 0,
    @SerialName("end_stat") val endStat: Int = 0,
    @SerialName("con_stat") val conStat: Int = 0,
) {
    companion object {
        const val ROLE_PLAYER = "player"
    }
}

/** The v2 player profile (`GET/PUT /api/v2/me/profile`). No weight, height or BMI. */
@Serializable
data class PlayerProfile(
    @SerialName("user_id") val userId: Int,
    @SerialName("display_name") val displayName: String = "",
    val goal: String = Goal.FITNESS.wire,
    val identity: String = "athlete",
    @SerialName("public_profile") val publicProfile: Boolean = false,
    @SerialName("location_consent") val locationConsent: Boolean = false,
    @SerialName("onboarding_completed") val onboardingCompleted: Boolean = false,
    @SerialName("referral_code") val referralCode: String = "",
    val city: String? = null,
    @SerialName("leaderboard_opt_in") val leaderboardOptIn: Boolean = false,
)

/** What the player wants from the app; sizes the daily quest. */
enum class Goal(val wire: String, val label: String, val description: String) {
    FITNESS("fitness", "Get fitter", "Short, doable quests that build up week by week."),
    RUNNING("running", "Run more", "Quests sized to your recent runs."),
    CONSISTENCY("consistency", "Build a habit", "Easy quests that make three active days a week stick."),
    COMPETITION("competition", "Compete", "Slightly harder quests, plus challenges and rankings.");

    companion object {
        fun fromWire(value: String): Goal = entries.firstOrNull { it.wire == value } ?: FITNESS
    }
}

/** Sign-up input, validated before it is sent. */
data class Registration(
    val email: String,
    val password: String,
    val displayName: String,
    val goal: Goal,
    val locationConsent: Boolean,
    val referralCode: String? = null,
    val inviteToken: String? = null,
) {
    /** Field errors keyed by field name; empty when valid. Same rules as the Flutter form. */
    fun validate(): Map<String, String> = buildMap {
        if (displayName.trim().length < 2) put(FIELD_NAME, "At least 2 characters")
        if (displayName.trim().length > 30) put(FIELD_NAME, "At most 30 characters")
        if (!email.contains('@')) put(FIELD_EMAIL, "Enter a valid email")
        if (password.length < 8) put(FIELD_PASSWORD, "At least 8 characters")
        // The server's bcrypt limit is in bytes; accents and emoji take more than one.
        if (password.encodeToByteArray().size > PASSWORD_MAX_BYTES) put(FIELD_PASSWORD, "At most 72 characters")
    }

    companion object {
        const val FIELD_NAME = "name"
        const val FIELD_EMAIL = "email"
        const val FIELD_PASSWORD = "password"
        const val PASSWORD_MAX_BYTES = 72
    }
}
