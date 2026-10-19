package com.osiris.shared.presentation

import com.osiris.shared.core.error.AppError
import com.osiris.shared.domain.exercise.Verdict
import com.osiris.shared.domain.model.Registration
import com.osiris.shared.domain.model.RunResult
import com.osiris.shared.domain.run.ActiveRun
import com.osiris.shared.domain.run.LocationFix
import com.osiris.shared.presentation.challenge.ChallengeDetailViewModel
import com.osiris.shared.presentation.common.Loadable
import com.osiris.shared.presentation.common.SharedViewModel as SharedViewModelLike
import com.osiris.shared.presentation.common.UiMessage
import com.osiris.shared.presentation.exercise.ExerciseHubViewModel
import com.osiris.shared.presentation.exercise.ExerciseSessionState.Phase
import com.osiris.shared.presentation.exercise.ExerciseSessionViewModel
import com.osiris.shared.presentation.run.RunDialog
import com.osiris.shared.presentation.run.RunViewModel
import com.osiris.shared.presentation.session.LoginViewModel
import com.osiris.shared.presentation.session.OnboardingState
import com.osiris.shared.presentation.session.OnboardingViewModel
import com.osiris.shared.presentation.settings.SettingsViewModel
import com.osiris.shared.presentation.today.TodayViewModel
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlin.time.Duration.Companion.hours
import kotlin.time.Duration.Companion.seconds
import kotlin.time.Instant
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runTest

class ViewModelTest {
    private val noon = Instant.parse("2026-06-21T12:00:00Z")
    private val midnight = Instant.parse("2026-12-21T23:30:00Z")
    private val amsterdam = LocationFix(52.37, 4.89)

    private fun TestScope.main() = UnconfinedTestDispatcher(testScheduler)

    /** Run view models tick every second; always stop them, or a failed assertion hangs the virtual clock. */
    private inline fun <T : SharedViewModelLike> T.use(block: T.() -> Unit) {
        try {
            block()
        } finally {
            clear()
        }
    }

    @Test
    fun `login shows the server's message and keeps the password for a retry`() = runTest {
        val auth = FakeAuth().apply { loginResult = fail(AppError.Unauthorized("Invalid email or password")) }
        val vm = LoginViewModel(auth, main())
        vm.onEmail("p@x.io")
        vm.onPassword("secret123")
        vm.submit()
        assertEquals("Invalid email or password", vm.state.value.error)
        assertEquals("secret123", vm.state.value.password)
        assertFalse(vm.state.value.busy)
    }

    @Test
    fun `sign-up never pre-ticks location consent and shows field errors before sending`() = runTest {
        val auth = FakeAuth()
        val vm = OnboardingViewModel(auth, FakePlayer(), dispatcher = main())
        assertFalse(vm.state.value.locationConsent)
        vm.next()
        vm.next()
        assertEquals(OnboardingState.Step.ACCOUNT, vm.state.value.step)
        vm.onEmail("nope")
        vm.create()
        assertEquals(setOf(Registration.FIELD_NAME, Registration.FIELD_EMAIL, Registration.FIELD_PASSWORD), vm.state.value.fieldErrors.keys)
        assertTrue(auth.registrations.isEmpty())
        vm.onName("Pat")
        vm.onEmail("p@x.io")
        vm.onPassword("secret123")
        vm.create()
        assertEquals(1, auth.registrations.size)
        assertFalse(auth.registrations.single().locationConsent)
    }

    @Test
    fun `a server-rejected email shows on the email field, other rejections as a message`() = runTest {
        val auth = FakeAuth().apply {
            registerResult = fail(AppError.Http(422, "INVALID_EMAIL", "Enter a valid email address"))
        }
        val vm = OnboardingViewModel(auth, FakePlayer(), dispatcher = main())
        vm.next()
        vm.next()
        vm.onName("Pat")
        vm.onEmail("pat@osiris.test")
        vm.onPassword("secret123")
        vm.create()
        assertEquals(mapOf(Registration.FIELD_EMAIL to "Enter a valid email address"), vm.state.value.fieldErrors)
        assertNull(vm.message.value)
        assertFalse(vm.state.value.busy)

        auth.registerResult = fail(AppError.Http(404, "REFERRAL_NOT_FOUND", "That invite code was not found"))
        vm.create()
        assertEquals(emptyMap(), vm.state.value.fieldErrors)
        assertEquals("That invite code was not found", vm.message.value?.text)
    }

    @Test
    fun `today keeps the screen on a failed refresh and says why`() = runTest {
        val player = FakePlayer()
        val vm = TodayViewModel(player, main())
        assertIs<Loadable.Ready<*>>(vm.state.value)
        player.todayResult = fail(AppError.Offline())
        vm.refresh()
        assertIs<Loadable.Ready<*>>(vm.state.value)
        assertEquals(UiMessage.Kind.ERROR, vm.message.value?.kind)
        assertEquals("app_opened", player.events.first().first)
    }

    @Test
    fun `a refused location says so instead of locating forever, and a fix clears it`() = runTest {
        RunViewModel(FakeRuns(), FakeChallenges(), FakePlayer(), clock = FixedClock(noon), dispatcher = main()).use {
            val vm = this
            assertEquals("LOCATING…", vm.state.value.actionLabel)
            vm.onLocationUnavailable(AppError.Validation("Location is off."))
            assertEquals("Location is off.", vm.state.value.locationProblem)
            assertEquals("LOCATION OFF", vm.state.value.actionLabel)
            assertFalse(vm.state.value.canStart)
            vm.onLocation(amsterdam)
            assertNull(vm.state.value.locationProblem)
            assertEquals("START RUN", vm.state.value.actionLabel)
        }
    }

    @Test
    fun `starting in the dark asks first, and the player can start anyway`() = runTest {
        val runs = FakeRuns()
        RunViewModel(runs, FakeChallenges(), FakePlayer(), clock = FixedClock(midnight), dispatcher = main()).use {
            val vm = this
            vm.onLocation(amsterdam)
            vm.start()
            assertEquals(RunDialog.LowLight, vm.state.value.dialog)
            assertNull(runs.active.value)
            vm.start(confirmedLowLight = true)
            assertTrue(vm.state.value.recording)
        }
    }

    @Test
    fun `a verified run celebrates, then offers to register the course`() = runTest {
        val clock = FixedClock(noon)
        val runs = FakeRuns()
        val challenges = FakeChallenges()
        RunViewModel(runs, challenges, FakePlayer(), clock = clock, dispatcher = main()).use {
            val vm = this
            vm.onLocation(amsterdam)
            vm.start()
            // Distance counts from the first fix after START, as in the Flutter app.
            vm.onLocation(amsterdam)
            clock.now += 30.seconds
            vm.onLocation(LocationFix(52.38, 4.89))
            assertEquals(2, runs.fixes.size)
            assertEquals("1.1 km", vm.state.value.distance)
            vm.finish()
            val celebrate = assertIs<RunDialog.Celebrate>(vm.state.value.dialog)
            assertEquals("Quest complete!", celebrate.title)
            assertEquals("2.40 km in 12:00", celebrate.summary)
            assertEquals("This week: 2 of 3 active days", celebrate.week)
            vm.dismissDialog()
            assertEquals(RunDialog.OfferCourse(11), vm.state.value.dialog)
            vm.registerCourse(11, "River loop")
            assertTrue("course 11 River loop" in challenges.calls)
        }
    }

    @Test
    fun `a challenge run submits the attempt and shows the result`() = runTest {
        val challenges = FakeChallenges()
        RunViewModel(FakeRuns(), challenges, FakePlayer(), challengeId = 3, clock = FixedClock(noon), dispatcher = main()).use {
            val vm = this
            vm.onLocation(amsterdam)
            vm.start()
            vm.finish()
            val info = assertIs<RunDialog.Info>(vm.state.value.dialog)
            assertEquals("Challenge won!", info.title)
            assertEquals("Your time: 10:00  •  Target: 10:50\n+30 XP", info.body)
            assertTrue("attempt 3 11" in challenges.calls)
        }
    }

    @Test
    fun `finishing offline keeps the run and explains`() = runTest {
        val runs = FakeRuns().apply { finishResult = fail(AppError.Offline()) }
        RunViewModel(runs, FakeChallenges(), FakePlayer(), clock = FixedClock(noon), dispatcher = main()).use {
            val vm = this
            vm.onLocation(amsterdam)
            vm.start()
            vm.finish()
            assertTrue(vm.state.value.recording)
            assertEquals("Points are saved on this phone. Tap FINISH again once you are back online.", vm.message.value?.text)
        }
    }

    @Test
    fun `a rejected run lists the reasons`() = runTest {
        val runs = FakeRuns().apply { finishResult = ok(RunResult("rejected", rejectionReason = "speed_implausible")) }
        RunViewModel(runs, FakeChallenges(), FakePlayer(), clock = FixedClock(noon), dispatcher = main()).use {
            val vm = this
            vm.onLocation(amsterdam)
            vm.start()
            vm.finish()
            val info = assertIs<RunDialog.Info>(vm.state.value.dialog)
            assertEquals("Run not verified", info.title)
            assertTrue(info.body.isNotBlank())
        }
    }

    @Test
    fun `a run left open for half a day asks whether to submit or discard`() = runTest {
        val old = ActiveRun(runId = 5, userId = 7, startedAt = noon - 13.hours)
        RunViewModel(FakeRuns(old), FakeChallenges(), FakePlayer(), clock = FixedClock(noon), dispatcher = main()).use {
            val vm = this
            assertEquals(RunDialog.StaleRun, vm.state.value.dialog)
            vm.discard()
            assertFalse(vm.state.value.recording)
        }
    }

    @Test
    fun `challenge routes are fetched only for the creator or a player who joined`() = runTest {
        val challenges = FakeChallenges()
        val vm = ChallengeDetailViewModel(3, challenges, FakePlayer(), main())
        assertTrue("course" !in challenges.calls)
        assertTrue(vm.state.value.canReport && vm.state.value.canInvite)
        challenges.challenge = challenges.challenge.copy(isMine = true)
        vm.refresh()
        assertTrue("course" in challenges.calls)
        assertFalse(vm.state.value.canReport)
    }

    @Test
    fun `invites are shared, and only a completed share is tracked`() = runTest {
        val player = FakePlayer()
        val vm = ChallengeDetailViewModel(3, FakeChallenges(), player, main())
        vm.invite()
        assertEquals("challenge_invite", vm.state.value.share?.kind)
        vm.shared(completed = false)
        assertTrue(player.events.none { it.first == "share_completed" })
        vm.invite()
        vm.shared(completed = true)
        assertEquals("challenge_invite", player.events.single { it.first == "share_completed" }.second["kind"])
    }

    @Test
    fun `the camera opens only after exercise consent`() = runTest {
        val exercises = FakeExercises()
        val vm = ExerciseHubViewModel(exercises, dispatcher = main())
        val pushup = catalog.byKey("pushup")!!
        vm.select(pushup)
        assertEquals(pushup, vm.state.value.askConsentFor)
        assertNull(vm.state.value.open)
        vm.consentAnswered(allow = false)
        assertNull(vm.state.value.open)
        vm.select(pushup)
        vm.consentAnswered(allow = true)
        assertEquals(pushup, vm.state.value.open)
        assertTrue(exercises.consented)
    }

    @Test
    fun `a recorded push-up set counts six reps, saves and shows the XP`() = runTest {
        val rec = recording("synthetic_pushup_6_full.json")
        val exercises = FakeExercises()
        val vm = ExerciseSessionViewModel(catalog.byKey("pushup")!!, catalog, exercises, clock = FixedClock(noon), dispatcher = main())
        rec.frames.take(5).forEach(vm::onFrame) // frames before START are ignored
        vm.start()
        rec.frames.forEach(vm::onFrame)
        assertEquals("6", vm.state.value.hud.count)
        vm.finish()
        assertEquals(Phase.DONE, vm.state.value.phase)
        val result = assertNotNull(vm.state.value.result)
        assertEquals(Verdict.VERIFIED, result.verdict)
        assertEquals("Push-ups: 6 reps", result.amount.replace(Regex("^[^:]+"), "Push-ups"))
        assertEquals("+15 XP", result.sync)
        assertEquals(6, exercises.saved.single().repsValid)
    }

    @Test
    fun `a set that cannot be saved says so`() = runTest {
        val exercises = FakeExercises().apply { saveResult = fail(AppError.Storage()) }
        val vm = ExerciseSessionViewModel(catalog.byKey("pushup")!!, catalog, exercises, dispatcher = main())
        vm.start()
        vm.finish()
        assertEquals("This set could not be saved on your phone.", vm.state.value.result?.sync)
    }

    @Test
    fun `QA recordings are saved only with a label`() = runTest {
        val rec = recording("synthetic_pushup_6_full.json")
        val exercises = FakeExercises()
        val vm = ExerciseSessionViewModel(catalog.byKey("pushup")!!, catalog, exercises, recordingAllowed = true, dispatcher = main())
        vm.setRecordLandmarks(true)
        vm.start()
        rec.frames.forEach(vm::onFrame)
        vm.finish()
        assertTrue(vm.state.value.askLabel)
        assertTrue(exercises.saved.isEmpty())
        vm.labelRecording("6")
        assertEquals(6, exercises.recordings.single().labelReps)
        assertEquals(rec.frames.size, exercises.recordings.single().frames.size)
        assertEquals(1, exercises.saved.size)
    }

    @Test
    fun `slow tracking warns, with hysteresis`() = runTest {
        val spec = catalog.byKey("pushup")!!
        val vm = ExerciseSessionViewModel(spec, catalog, FakeExercises(), dispatcher = main())
        val slowGap = (1000 / (spec.minPoseFps / 2)).toLong()
        var t = 0L
        repeat(20) { vm.onFrame(com.osiris.shared.domain.exercise.PoseFrame(t, emptyMap())); t += slowGap }
        assertNotNull(vm.state.value.slowWarning)
        repeat(20) { vm.onFrame(com.osiris.shared.domain.exercise.PoseFrame(t, emptyMap())); t += 33 }
        assertNull(vm.state.value.slowWarning)
    }

    @Test
    fun `settings builds the invite text and the rules page`() = runTest {
        val vm = SettingsViewModel(FakeAuth(), FakePlayer(), FakePrivacy(), FakeExercises(), main())
        assertEquals("Goal  •  you are an athlete", vm.state.value.identityLine)
        vm.shareInvite()
        assertEquals(
            "Join me on Osiris: daily running and walking quests. Use my code ABC. https://osiris.example/r/ABC",
            vm.state.value.share?.text,
        )
        vm.shared(true)
        vm.loadRules()
        assertEquals(listOf("Runs are checked for speed."), vm.state.value.rules!!.first { it.title == "How runs are checked" }.lines)
    }
}
