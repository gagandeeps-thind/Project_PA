package com.osiris.shared.presentation

import com.osiris.shared.core.error.AppError
import com.osiris.shared.core.error.Outcome
import com.osiris.shared.domain.exercise.ExerciseCatalog
import com.osiris.shared.domain.exercise.PoseRecording
import com.osiris.shared.domain.exercise.SessionSummary
import com.osiris.shared.domain.model.AttemptSummary
import com.osiris.shared.domain.model.ChallengeDraft
import com.osiris.shared.domain.model.ChallengeSummary
import com.osiris.shared.domain.model.CourseRoute
import com.osiris.shared.domain.model.CourseSummary
import com.osiris.shared.domain.model.BoardExercise
import com.osiris.shared.domain.model.BoardKind
import com.osiris.shared.domain.model.BoardPeriod
import com.osiris.shared.domain.model.Community
import com.osiris.shared.domain.model.ExerciseHistory
import com.osiris.shared.domain.model.GlobalBoard
import com.osiris.shared.domain.model.HubChallenge
import com.osiris.shared.domain.model.HubSection
import com.osiris.shared.domain.model.Leaderboard
import com.osiris.shared.domain.model.Season
import com.osiris.shared.domain.model.SeasonLeaderboard
import com.osiris.shared.domain.model.PlayerProfile
import com.osiris.shared.domain.model.Progression
import com.osiris.shared.domain.model.Quest
import com.osiris.shared.domain.model.ReferralSummary
import com.osiris.shared.domain.model.Registration
import com.osiris.shared.domain.model.ReportReason
import com.osiris.shared.domain.model.RunResult
import com.osiris.shared.domain.model.SetOutcome
import com.osiris.shared.domain.model.ShareCard
import com.osiris.shared.domain.model.TodayData
import com.osiris.shared.domain.model.UserProfile
import com.osiris.shared.domain.model.WeeklyGoal
import com.osiris.shared.domain.repository.AuthRepository
import com.osiris.shared.domain.repository.AuthState
import com.osiris.shared.domain.repository.ChallengeRepository
import com.osiris.shared.domain.repository.CommunityRepository
import com.osiris.shared.domain.repository.ExerciseRepository
import com.osiris.shared.domain.repository.PlayerRepository
import com.osiris.shared.domain.repository.RunRepository
import com.osiris.shared.domain.run.ActiveRun
import com.osiris.shared.domain.run.AutoPause
import com.osiris.shared.domain.run.LatLng
import com.osiris.shared.domain.run.LocationFix
import com.osiris.shared.domain.run.Sport
import java.io.File
import kotlin.time.Clock
import kotlin.time.Instant
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.serialization.json.JsonObject

class FixedClock(var now: Instant) : Clock {
    override fun now(): Instant = now
}

fun <T> ok(value: T): Outcome<T> = Outcome.Success(value)
fun fail(error: AppError): Outcome<Nothing> = Outcome.Failure(error)

val catalog: ExerciseCatalog by lazy { ExerciseCatalog.parse(File(System.getProperty("osiris.catalog")).readText()) }

fun recording(name: String): PoseRecording =
    PoseRecording.parse(File(System.getProperty("osiris.recordings"), name).readText())

class FakeAuth : AuthRepository {
    override val state = MutableStateFlow<AuthState>(AuthState.SignedOut)
    var loginResult: Outcome<UserProfile> = ok(UserProfile(id = 7))
    val registrations = mutableListOf<Registration>()
    var registerResult: Outcome<UserProfile> = ok(UserProfile(id = 7))
    override suspend fun restore() {
        state.value = AuthState.SignedOut
    }
    override suspend fun login(email: String, password: String) = loginResult.also {
        it.getOrNull()?.let { u -> state.value = AuthState.SignedIn(u) }
    }
    override suspend fun register(registration: Registration): Outcome<UserProfile> {
        registrations += registration
        return registerResult
    }
    override suspend fun signOutEverywhere() = ok(Unit)
    override suspend fun logout() {
        state.value = AuthState.SignedOut
    }
    override suspend fun onSessionExpired() = logout()
}

fun quest(completed: Boolean = false) = Quest(key = "q", kind = "daily", title = "Walk 1 km", targetM = 1000, completed = completed)

val today = TodayData(today = quest(completed = true), tomorrow = quest().copy(title = "Run 2 km"), week = WeeklyGoal(activeDays = 2))

class FakePlayer : PlayerRepository {
    val events = mutableListOf<Pair<String, Map<String, String>>>()
    var todayResult: Outcome<TodayData> = ok(today)
    val todayPositions = mutableListOf<LatLng?>()
    override suspend fun today(position: LatLng?) = todayResult.also { todayPositions += position }
    override suspend fun profile() = ok(PlayerProfile(userId = 7, identity = "athlete"))
    override suspend fun updateProfile(changes: JsonObject) = ok(PlayerProfile(userId = 7))
    var progressionResult: Outcome<Progression> = ok(Progression(xp = 120, nextRankXp = 200))
    override suspend fun progression() = progressionResult
    override suspend fun referrals() = ok(ReferralSummary(code = "ABC", url = "https://osiris.example/r/ABC"))
    override suspend fun shareAchievement(kind: String, entityId: Int) = ok(ShareCard("t", "https://osiris.example/s/t"))
    override suspend fun track(event: String, properties: Map<String, String>) {
        events += event to properties
    }
}

class FakeRuns(initial: ActiveRun? = null) : RunRepository {
    override val active = MutableStateFlow(initial)
    override val offline = MutableStateFlow(false)
    val fixes = mutableListOf<LocationFix>()
    var finishResult: Outcome<RunResult> = ok(RunResult("accepted", distanceM = 2400.0, durationSeconds = 720.0, xpAwarded = 40))
    override suspend fun bindAccount(userId: Int?) = Unit
    override suspend fun start(challengeId: Int?, now: Instant, sport: Sport, autoPause: AutoPause): Outcome<ActiveRun> {
        val run = ActiveRun(
            runId = 11, userId = 7, startedAt = now, challengeId = challengeId, sport = sport.wire,
            autoPause = autoPause.on, autoPauseMps = if (autoPause.on) autoPause.mps else ActiveRun.MOVING_MIN_MPS,
        )
        active.value = run
        return ok(run)
    }
    override suspend fun addFix(fix: LocationFix, now: Instant) {
        fixes += fix
        active.value = active.value?.withFix(fix, now)
    }
    override suspend fun flush() = ok(true)
    override suspend fun finish(now: Instant): Outcome<RunResult> =
        finishResult.also { if (it.isSuccess) active.value = null }
    override suspend fun discard() {
        active.value = null
    }
}

class FakeChallenges : ChallengeRepository {
    var challenge = ChallengeSummary(id = 3, title = "Park loop", status = "open")
    val calls = mutableListOf<String>()
    var attempt = AttemptSummary(id = 1, challengeId = 3, status = "completed", outcome = "won", elapsedSeconds = 600.0, targetSeconds = 650.0, xpAwarded = 30)
    override suspend fun nearby(position: LatLng, radiusKm: Double) = ok(listOf(challenge))
    override suspend fun challenge(id: Int) = ok(challenge)
    override suspend fun course(challengeId: Int): Outcome<CourseRoute> {
        calls += "course"
        return ok(CourseRoute())
    }
    override suspend fun join(challengeId: Int): Outcome<Unit> {
        calls += "join"
        return ok(Unit)
    }
    override suspend fun submitAttempt(challengeId: Int, runId: Int): Outcome<AttemptSummary> {
        calls += "attempt $challengeId $runId"
        return ok(attempt)
    }
    override suspend fun myCourses() = ok(emptyList<CourseSummary>())
    override suspend fun registerCourse(runId: Int, name: String): Outcome<Unit> {
        calls += "course $runId $name"
        return ok(Unit)
    }
    override suspend fun publish(draft: ChallengeDraft) = ok(9)
    override suspend fun invite(challengeId: Int) = ok("Race me: https://osiris.example/i/x")
    override suspend fun report(challengeId: Int, reason: ReportReason) = ok("Thanks, we'll look at it.")
    override suspend fun blockCreator(challengeId: Int): Outcome<Unit> {
        calls += "block"
        return ok(Unit)
    }
    var hub: Map<HubSection, Outcome<List<HubChallenge>>> = emptyMap()
    override suspend fun hub(section: HubSection) = hub[section] ?: ok(emptyList())
}

/** Global boards are answered by [boards]; a test can suspend one to model a slow response. */
class FakeCommunities : CommunityRepository {
    var boards: suspend (BoardKind, BoardPeriod, BoardExercise) -> Outcome<GlobalBoard> =
        { kind, period, _ -> ok(GlobalBoard(board = kind.wire, period = period.wire, unit = "km")) }
    override suspend fun globalBoard(kind: BoardKind, period: BoardPeriod, exercise: BoardExercise) =
        boards(kind, period, exercise)
    override suspend fun discover(city: String?) = ok(emptyList<Community>())
    override suspend fun mine() = ok(emptyList<Community>())
    override suspend fun community(slug: String) = ok(Community(slug, slug))
    override suspend fun join(slug: String, joinCode: String?) = ok(Community(slug, slug, myRole = "member"))
    override suspend fun leave(slug: String) = ok(Unit)
    override suspend fun leaderboard(slug: String) = ok(Leaderboard())
    override suspend fun challenges(slug: String) = ok(emptyList<ChallengeSummary>())
    override suspend fun local() = ok(Leaderboard())
    override suspend fun seasons() = ok(emptyList<Season>())
    override suspend fun joinSeason(slug: String) = ok(Unit)
    override suspend fun seasonLeaderboard(slug: String) = ok(SeasonLeaderboard())
    override suspend fun report(slug: String) = ok("Thanks.")
}

class FakeExercises : ExerciseRepository {
    var consented = false
    var saveResult: Outcome<SetOutcome> = ok(SetOutcome(uploaded = true, xpAwarded = 15))
    val saved = mutableListOf<SessionSummary>()
    val recordings = mutableListOf<PoseRecording>()
    override suspend fun bindAccount(userId: Int?) = Unit
    override suspend fun catalog() = ok(catalog)
    override suspend fun consent() = consented
    override suspend fun setConsent(granted: Boolean, deleteData: Boolean): Outcome<Boolean> {
        consented = granted
        return ok(granted)
    }
    override suspend fun saveSet(summary: SessionSummary, startedAt: Instant): Outcome<SetOutcome> {
        saved += summary
        return saveResult
    }
    override suspend fun history() = ExerciseHistory.EMPTY
    override suspend fun sync() = false
    override suspend fun saveRecording(recording: PoseRecording): Outcome<String> {
        recordings += recording
        return ok("/tmp/${recording.exerciseKey}.json")
    }
}

class FakePrivacy : com.osiris.shared.domain.repository.PrivacyRepository {
    override suspend fun blocks() = ok(emptyList<com.osiris.shared.domain.model.BlockEntry>())
    override suspend fun unblock(blockId: Int) = ok(Unit)
    override suspend fun export() = ok(JsonObject(emptyMap()))
    override suspend fun erase(password: String) = ok(Unit)
    override suspend fun rules() = ok(
        kotlinx.serialization.json.buildJsonObject {
            put("verification", kotlinx.serialization.json.JsonArray(listOf(kotlinx.serialization.json.JsonPrimitive("Runs are checked for speed."))))
        },
    )
}

class FakeDeviceSetup(primerDone: Boolean = false) : com.osiris.shared.domain.repository.DeviceSetupRepository {
    override val primerCompleted = MutableStateFlow(primerDone)
    override val telemetryConsent = MutableStateFlow(false)
    override suspend fun completePrimer() {
        primerCompleted.value = true
    }
    override suspend fun setTelemetryConsent(granted: Boolean) {
        telemetryConsent.value = granted
    }
}
