package com.osiris.shared.presentation

import com.osiris.shared.core.error.AppError
import com.osiris.shared.core.error.Outcome
import com.osiris.shared.domain.model.ActivityKind
import com.osiris.shared.domain.model.Connection
import com.osiris.shared.domain.model.FeedPost
import com.osiris.shared.domain.model.GroupChallenge
import com.osiris.shared.domain.model.GroupChallenges
import com.osiris.shared.domain.model.NewGroupChallenge
import com.osiris.shared.domain.model.NewTrainingSession
import com.osiris.shared.domain.model.Quote
import com.osiris.shared.domain.model.StartMode
import com.osiris.shared.domain.model.TrainingActivity
import com.osiris.shared.domain.model.TrainingProgress
import com.osiris.shared.domain.model.TrainingSession
import com.osiris.shared.domain.model.TrainingSummary
import com.osiris.shared.domain.model.WeeklyProgress
import com.osiris.shared.domain.repository.GroupChallengeRepository
import com.osiris.shared.domain.repository.TrainingRepository
import com.osiris.shared.domain.run.LocationFix
import com.osiris.shared.domain.training.Channel
import com.osiris.shared.presentation.start.GroupChallengeDetailViewModel
import com.osiris.shared.presentation.start.GroupChallengesViewModel
import com.osiris.shared.presentation.start.LiveSessionViewModel
import com.osiris.shared.presentation.start.LivePhase
import com.osiris.shared.presentation.start.ProgressViewModel
import com.osiris.shared.presentation.start.StartViewModel
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlin.time.Clock
import kotlin.time.Instant
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runTest

private val run = TrainingActivity("run", "Run", ActivityKind.GPS, "distance_m", 12.5, gps = true)
private val pushup = TrainingActivity("pushup", "Push-up", ActivityKind.CAMERA, "reps")
private val t0 = Instant.fromEpochSeconds(1_800_000_000)

private fun saved(id: Int = 9, key: String = "run") =
    TrainingSession(id = id, activityKey = key, mode = "train", source = "sensor", startedAt = t0, durationS = 60.0)

private fun group(id: Int, myStatus: String? = null) = GroupChallenge(
    id = id, title = "G$id", activityKey = "run", metric = "distance_m", target = 1000.0,
    startsAt = t0, endsAt = t0, myStatus = myStatus,
)

class FakeTraining : TrainingRepository {
    val summaries = mutableListOf<String>()
    val uploads = mutableListOf<NewTrainingSession>()
    val posts = mutableListOf<Pair<Int, String>>()
    val sessionQueries = mutableListOf<String?>()
    var uploadFails = 0

    override suspend fun activities() = ok(listOf(run, pushup))
    override suspend fun quote() = ok(Quote(1, "Go", "Osiris"))
    override suspend fun summary(activityKey: String) = ok(TrainingSummary(activityKey)).also { summaries += activityKey }
    override suspend fun sessions(activityKey: String?, offset: Int): Outcome<List<TrainingSession>> {
        sessionQueries += activityKey
        return ok(listOf(saved()))
    }
    override suspend fun session(id: Int) = ok(saved(id))
    override suspend fun upload(session: NewTrainingSession): Outcome<TrainingSession> {
        uploads += session
        if (uploadFails > 0) {
            uploadFails--
            return Outcome.Failure(AppError.Offline())
        }
        return ok(saved(key = session.activityKey))
    }
    override suspend fun post(sessionId: Int, caption: String): Outcome<FeedPost> {
        posts += sessionId to caption
        return ok(FeedPost(id = 3, userId = 7))
    }
    override suspend fun progress(weeks: Int) = ok(TrainingProgress(listOf(WeeklyProgress("2026-10-26", 600.0, 1))))
    override suspend fun connections() = ok(listOf(Connection(4, "Ana")))
}

class FakeGroups : GroupChallengeRepository {
    var loads = 0
    val created = mutableListOf<NewGroupChallenge>()
    val joined = mutableListOf<Int>()
    override suspend fun all(): Outcome<GroupChallenges> {
        loads++
        return ok(GroupChallenges(official = listOf(group(1)), invited = listOf(group(2, "invited"))))
    }
    override suspend fun detail(id: Int) = ok(group(id))
    override suspend fun create(challenge: NewGroupChallenge) = ok(group(5, "joined")).also { created += challenge }
    override suspend fun join(id: Int) = ok(group(id, "joined")).also { joined += id }
    override suspend fun leave(id: Int) = ok(group(id))
    val cancelled = mutableListOf<Int>()
    override suspend fun cancel(id: Int) = ok(group(id).copy(status = "cancelled")).also { cancelled += id }
}

private object StepClock : Clock {
    var now: Instant = t0
    override fun now() = now
}

class StartViewModelTest {
    private fun TestScope.main() = UnconfinedTestDispatcher(testScheduler)

    private fun TestScope.start(mode: StartMode, training: FakeTraining = FakeTraining(), groups: FakeGroups = FakeGroups()) =
        StartViewModel(training, groups, FakePlayer(), mode, StepClock, main())

    @Test
    fun `select reloads summary`() = runTest {
        val training = FakeTraining()
        val vm = start(StartMode.TRAIN, training)
        assertEquals("run", vm.state.value.selected?.key)
        assertEquals("Go", vm.state.value.quote?.text)
        vm.select(pushup)
        assertEquals(listOf("run", "pushup"), training.summaries)
        assertEquals("pushup", vm.state.value.summary?.valueOrNull?.activityKey)
        vm.clear()
    }

    @Test
    fun `challenge mode loads groups and suggested and train mode does not`() = runTest {
        val groups = FakeGroups()
        val training = FakeTraining()
        val challenge = start(StartMode.CHALLENGE, training, groups)
        assertEquals(1, groups.loads)
        assertEquals(listOf(1), challenge.state.value.groups?.valueOrNull?.official?.map { it.id })
        assertTrue(challenge.state.value.suggested.isNotEmpty())
        assertTrue(training.summaries.isEmpty())
        start(StartMode.TRAIN, FakeTraining(), groups)
        assertEquals(1, groups.loads)
        challenge.clear()
    }

    @Test
    fun `camera set saves a linked session and offers post or save`() = runTest {
        val training = FakeTraining()
        val vm = start(StartMode.CHALLENGE, training)
        vm.saveCameraSet("pushup", setId = "set-44", startedAt = t0)
        val upload = training.uploads.single()
        assertEquals("set-44", upload.exerciseSetId)
        assertEquals("camera", upload.source)
        assertEquals("challenge", upload.mode)
        assertNotNull(vm.state.value.pendingPost)
        vm.post("")
        assertEquals(listOf(9 to ""), training.posts)
        assertNull(vm.state.value.pendingPost)
        vm.clear()
    }
}

class LiveSessionViewModelTest {
    private fun TestScope.live(training: FakeTraining, mode: StartMode = StartMode.TRAIN) =
        LiveSessionViewModel(training, run, mode, StepClock, UnconfinedTestDispatcher(testScheduler), tick = false)

    @Test
    fun `stop uploads once and offers post or save`() = runTest {
        StepClock.now = t0
        val training = FakeTraining()
        val vm = live(training, StartMode.CHALLENGE)
        vm.onSample(Channel.HR, 120.0)
        vm.onFix(LocationFix(45.0, -66.0, accuracyM = 5.0, speedMps = 2.0, altitudeM = 10.0))
        assertEquals(120.0, vm.state.value.live[Channel.HR])
        StepClock.now = Instant.fromEpochSeconds(t0.epochSeconds + 90)
        vm.stop()
        vm.stop()
        val upload = training.uploads.single()
        assertEquals("challenge", upload.mode)
        assertEquals(90.0, upload.durationS)
        assertEquals(listOf(listOf(0.0, 120.0)), upload.series.hr)
        assertEquals(LivePhase.SAVED, vm.state.value.phase)
        vm.clear()
    }

    @Test
    fun `failed upload keeps the session and retry reuses the client id`() = runTest {
        StepClock.now = t0
        val training = FakeTraining().apply { uploadFails = 1 }
        val vm = live(training)
        StepClock.now = Instant.fromEpochSeconds(t0.epochSeconds + 30)
        vm.stop()
        assertEquals(LivePhase.FAILED, vm.state.value.phase)
        vm.retry()
        assertEquals(LivePhase.SAVED, vm.state.value.phase)
        assertEquals(2, training.uploads.size)
        assertEquals(training.uploads[0], training.uploads[1])
        vm.clear()
    }

    @Test
    fun `post marks posted and keep finishes without posting`() = runTest {
        val training = FakeTraining()
        val vm = live(training)
        vm.stop()
        vm.post("Morning run")
        assertTrue(vm.state.value.posted && vm.state.value.finished)
        assertEquals(listOf(9 to "Morning run"), training.posts)
        val other = live(FakeTraining())
        other.stop()
        other.keep()
        assertTrue(other.state.value.finished && !other.state.value.posted)
        vm.clear()
        other.clear()
    }

    @Test
    fun `paused samples are dropped`() = runTest {
        val vm = live(FakeTraining())
        vm.pause()
        vm.onSample(Channel.POWER, 200.0)
        assertTrue(vm.state.value.paused)
        assertNull(vm.state.value.live[Channel.POWER])
        vm.resume()
        vm.onSample(Channel.POWER, 210.0)
        assertEquals(210.0, vm.state.value.live[Channel.POWER])
        vm.clear()
    }
}

class GroupChallengeViewModelsTest {
    @Test
    fun `create sends invitees and reloads the lists`() = runTest {
        val groups = FakeGroups()
        val vm = GroupChallengesViewModel(groups, FakeTraining(), UnconfinedTestDispatcher(testScheduler))
        assertEquals(listOf(4), vm.state.value.connections.map { it.userId })
        vm.create(NewGroupChallenge("Weekend 20k", "run", "distance_m", 20000.0, 7, listOf(4)))
        assertEquals(listOf(4), groups.created.single().inviteeIds)
        assertEquals(2, groups.loads)
        assertEquals(5, vm.state.value.created?.id)
        vm.clear()
    }

    @Test
    fun `join updates the detail`() = runTest {
        val groups = FakeGroups()
        val vm = GroupChallengeDetailViewModel(7, groups, UnconfinedTestDispatcher(testScheduler))
        vm.join()
        assertEquals(listOf(7), groups.joined)
        assertTrue(vm.state.value.challenge.valueOrNull!!.joined)
        vm.cancel()
        assertEquals(listOf(7), groups.cancelled)
        assertEquals("cancelled", vm.state.value.challenge.valueOrNull!!.status)
        vm.clear()
    }

    @Test
    fun `progress loads weeks and filters sessions by activity`() = runTest {
        val training = FakeTraining()
        val vm = ProgressViewModel(training, UnconfinedTestDispatcher(testScheduler))
        assertEquals(1, vm.state.value.weeks.size)
        vm.filter("run")
        assertEquals(listOf(null, "run"), training.sessionQueries)
        vm.open(9)
        assertEquals(9, vm.state.value.detail?.id)
        vm.clear()
    }
}
