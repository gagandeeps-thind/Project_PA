package com.osiris.shared.domain.repository

import com.osiris.shared.core.error.Outcome
import com.osiris.shared.domain.exercise.ExerciseCatalog
import com.osiris.shared.domain.exercise.PoseRecording
import com.osiris.shared.domain.exercise.SessionSummary
import com.osiris.shared.domain.model.AttemptSummary
import com.osiris.shared.domain.model.BlockEntry
import com.osiris.shared.domain.model.ChallengeDraft
import com.osiris.shared.domain.model.ChallengeSummary
import com.osiris.shared.domain.model.Community
import com.osiris.shared.domain.model.CourseRoute
import com.osiris.shared.domain.model.CourseSummary
import com.osiris.shared.domain.model.ExerciseHistory
import com.osiris.shared.domain.model.Leaderboard
import com.osiris.shared.domain.model.SeasonLeaderboard
import com.osiris.shared.domain.model.PlayerProfile
import com.osiris.shared.domain.model.Progression
import com.osiris.shared.domain.model.ReferralSummary
import com.osiris.shared.domain.model.Registration
import com.osiris.shared.domain.model.ReportReason
import com.osiris.shared.domain.model.Season
import com.osiris.shared.domain.model.SetOutcome
import com.osiris.shared.domain.model.ShareCard
import com.osiris.shared.domain.model.TodayData
import com.osiris.shared.domain.model.UserProfile
import com.osiris.shared.domain.run.LatLng
import kotlin.time.Instant
import kotlinx.coroutines.flow.StateFlow
import kotlinx.serialization.json.JsonObject

/*
 * Contracts between the business logic and the data layer. View models depend on these
 * interfaces only, so they are tested with fakes and never see HTTP, SQL or platform storage.
 * Every call that can fail returns an [Outcome]; none throws, except for coroutine cancellation.
 */

/** Who is signed in. */
sealed interface AuthState {
    /** Session restore has not finished yet (app start). */
    data object Restoring : AuthState
    data object SignedOut : AuthState
    data class SignedIn(val user: UserProfile) : AuthState
}

/** Data that belongs to one account on this phone and must be cleared when the account changes. */
fun interface AccountScoped {
    suspend fun bindAccount(userId: Int?)
}

interface AuthRepository {
    val state: StateFlow<AuthState>

    /** Restores the stored session, if any. Players only; other roles are signed out. */
    suspend fun restore()

    /** Signs a player in. Merchants and admins are refused with a validation error. */
    suspend fun login(email: String, password: String): Outcome<UserProfile>

    /** BMI-free sign-up; signs the player in on success. */
    suspend fun register(registration: Registration): Outcome<UserProfile>

    /** Signs out every other device; this one keeps a fresh token. */
    suspend fun signOutEverywhere(): Outcome<Unit>

    suspend fun logout()

    /** Called by the network layer when the server answers 401: the session is gone. */
    suspend fun onSessionExpired()
}

interface PlayerRepository {
    suspend fun today(position: LatLng?): Outcome<TodayData>
    suspend fun profile(): Outcome<PlayerProfile>
    suspend fun updateProfile(changes: JsonObject): Outcome<PlayerProfile>
    suspend fun progression(): Outcome<Progression>
    suspend fun referrals(): Outcome<ReferralSummary>
    suspend fun shareAchievement(kind: String, entityId: Int): Outcome<ShareCard>

    /** Anonymous funnel event; never fails the caller. */
    suspend fun track(event: String, properties: Map<String, String> = emptyMap())
}

interface ChallengeRepository {
    suspend fun nearby(position: LatLng, radiusKm: Double = 5.0): Outcome<List<ChallengeSummary>>
    suspend fun challenge(id: Int): Outcome<ChallengeSummary>
    suspend fun course(challengeId: Int): Outcome<CourseRoute>
    suspend fun join(challengeId: Int): Outcome<Unit>
    suspend fun submitAttempt(challengeId: Int, runId: Int): Outcome<AttemptSummary>
    suspend fun myCourses(): Outcome<List<CourseSummary>>
    suspend fun registerCourse(runId: Int, name: String): Outcome<Unit>
    /** Publishes a challenge; returns its id. */
    suspend fun publish(draft: ChallengeDraft): Outcome<Int>
    /** Share text with an invite link that carries the player's referral. */
    suspend fun invite(challengeId: Int): Outcome<String>
    /** Returns the server's acknowledgement for the player. */
    suspend fun report(challengeId: Int, reason: ReportReason): Outcome<String>
    suspend fun blockCreator(challengeId: Int): Outcome<Unit>
}

interface CommunityRepository {
    suspend fun discover(city: String? = null): Outcome<List<Community>>
    suspend fun mine(): Outcome<List<Community>>
    suspend fun community(slug: String): Outcome<Community>
    /** Joins and returns the community with the player's new role. */
    suspend fun join(slug: String, joinCode: String? = null): Outcome<Community>
    suspend fun leave(slug: String): Outcome<Unit>
    suspend fun leaderboard(slug: String): Outcome<Leaderboard>
    suspend fun challenges(slug: String): Outcome<List<ChallengeSummary>>
    suspend fun local(): Outcome<Leaderboard>
    suspend fun seasons(): Outcome<List<Season>>
    suspend fun joinSeason(slug: String): Outcome<Unit>
    suspend fun seasonLeaderboard(slug: String): Outcome<SeasonLeaderboard>
    /** Reports a community as spam; returns the server's acknowledgement. */
    suspend fun report(slug: String): Outcome<String>
}

interface PrivacyRepository {
    suspend fun blocks(): Outcome<List<BlockEntry>>
    suspend fun unblock(blockId: Int): Outcome<Unit>
    /** The player's data export, as the server sends it. */
    suspend fun export(): Outcome<JsonObject>
    /** Erases the account; signs out on success. */
    suspend fun erase(password: String): Outcome<Unit>
    suspend fun rules(): Outcome<JsonObject>
}

interface ExerciseRepository : AccountScoped {
    /** Cached server catalog, else the bundled one; refreshes in the background. */
    suspend fun catalog(): Outcome<ExerciseCatalog>

    /** Server consent with an offline fallback to the last known answer for this account. */
    suspend fun consent(): Boolean
    suspend fun setConsent(granted: Boolean, deleteData: Boolean = false): Outcome<Boolean>

    /** Saves a finished set on the phone, then tries to upload everything pending. */
    suspend fun saveSet(summary: SessionSummary, startedAt: Instant): Outcome<SetOutcome>

    /** Local history (instant, offline). */
    suspend fun history(): ExerciseHistory

    /** Retries pending uploads and pulls review outcomes. True when local data changed. */
    suspend fun sync(): Boolean

    /** Debug and QA builds only: saves a labeled landmark recording; returns where. */
    suspend fun saveRecording(recording: PoseRecording): Outcome<String>
}
