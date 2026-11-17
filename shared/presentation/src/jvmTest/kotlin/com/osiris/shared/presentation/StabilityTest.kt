package com.osiris.shared.presentation

import com.osiris.shared.core.error.AppError
import com.osiris.shared.core.error.Outcome
import com.osiris.shared.domain.model.DirectMessage
import com.osiris.shared.domain.model.FeedPost
import com.osiris.shared.domain.model.MessageThread
import com.osiris.shared.domain.model.SocialUser
import com.osiris.shared.domain.model.SupportMessage
import com.osiris.shared.domain.repository.PlayerRepository
import com.osiris.shared.domain.repository.SupportChatRepository
import com.osiris.shared.domain.run.LocationFix
import com.osiris.shared.presentation.common.UiMessage
import com.osiris.shared.presentation.run.RunViewModel
import com.osiris.shared.presentation.social.ChatViewModel
import com.osiris.shared.presentation.start.ProgressViewModel
import com.osiris.shared.presentation.support.SupportChatState.Status
import com.osiris.shared.presentation.support.SupportChatViewModel
import com.osiris.shared.presentation.today.TodayViewModel
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlin.time.Instant
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.channels.ReceiveChannel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runTest

/** Each home section answers after [LATENCY_MS], to tell loading side by side from one after another. */
private class SlowPlayer(private val base: FakePlayer = FakePlayer()) : PlayerRepository by base {
    override suspend fun notifications() = base.notifications().also { delay(LATENCY_MS) }
    override suspend fun suggestedChallenges() = base.suggestedChallenges().also { delay(LATENCY_MS) }
    override suspend fun suggestedOsirians() = base.suggestedOsirians().also { delay(LATENCY_MS) }
    override suspend fun feedPosts(limit: Int, offset: Int) = base.feedPosts(limit, offset).also { delay(LATENCY_MS) }

    companion object {
        const val LATENCY_MS = 100L
    }
}

/** Counts connections and holds each one open until it is cancelled. */
private class CountingSupport : SupportChatRepository {
    var opened = 0
    var open = 0
    override fun open(outgoing: ReceiveChannel<String>): Flow<SupportMessage> = flow {
        opened++
        open++
        try {
            emit(SupportMessage("support", "Hi", Instant.parse("2026-10-19T15:00:00Z")))
            awaitCancellation()
        } finally {
            open--
        }
    }
}

class StabilityTest {
    private val noon = Instant.parse("2026-06-21T12:00:00Z")
    private val amsterdam = LocationFix(52.37, 4.89)

    private fun TestScope.main() = UnconfinedTestDispatcher(testScheduler)

    @Test
    fun `a failure nothing caught is shown as an error and the view model keeps working`() = runTest {
        val runs = FakeRuns()
        val vm = RunViewModel(runs, FakeChallenges(), FakePlayer(), clock = FixedClock(noon), dispatcher = main())
        vm.onLocation(amsterdam)
        vm.start()
        runs.addFixError = AppError.Storage("Could not save the run on this phone.")
        vm.onLocation(amsterdam)
        assertEquals(UiMessage("Could not save the run on this phone.", UiMessage.Kind.ERROR), vm.message.value)

        // The scope survived: the next fix is recorded.
        runs.addFixError = null
        vm.onLocation(amsterdam)
        assertEquals(1, runs.fixes.size)

        runs.addFixError = IllegalStateException("not an AppError")
        vm.onLocation(amsterdam)
        assertEquals(AppError.Unexpected().userMessage, vm.message.value?.text)
        vm.clear()
    }

    @Test
    fun `a position for display moves the map and the route line without recording a fix`() = runTest {
        val runs = FakeRuns()
        val vm = RunViewModel(runs, FakeChallenges(), FakePlayer(), clock = FixedClock(noon), dispatcher = main())
        vm.onPosition(amsterdam)
        vm.start()
        vm.onPosition(LocationFix(52.38, 4.89))
        assertTrue(vm.state.value.recording)
        assertEquals(2, vm.state.value.trace.size)
        assertTrue(runs.fixes.isEmpty())
        vm.clear()
    }

    @Test
    fun `chat stops polling and marking read while paused and catches up on resume`() = runTest {
        fun message(id: Int) = DirectMessage(id, 2, 1, "m$id", noon, read = false, mine = false)
        val social = FakeSocial()
        val vm = ChatViewModel(2, social, main(), pollMs = 1_000)
        assertEquals(1, social.threadCalls.size)
        vm.pause()
        social.threadResult = Outcome.Success(MessageThread(SocialUser(2, "Player 2", "h2"), true, listOf(message(1), message(2))))
        advanceTimeBy(10_000)
        assertEquals(1, social.threadCalls.size)
        assertEquals(listOf(2), social.readMarks)

        vm.resume()
        vm.resume() // already polling: no second loop
        assertEquals(listOf(1, 2), vm.state.value.messages.valueOrNull!!.map { it.id })
        advanceTimeBy(1_001)
        assertEquals(3, social.threadCalls.size)
        vm.clear()
    }

    @Test
    fun `support chat closes its socket while paused without ending the chat, and reopens on resume`() = runTest {
        val support = CountingSupport()
        val vm = SupportChatViewModel(support, dispatcher = main())
        assertEquals(1, support.open)
        vm.pause()
        vm.pause()
        assertEquals(0, support.open)
        assertEquals(Status.OPEN, vm.state.value.status)
        assertNull(vm.state.value.error)

        vm.resume()
        vm.resume()
        assertEquals(1, support.open)
        assertEquals(2, support.opened)
        assertEquals(Status.OPEN, vm.state.value.status)
        vm.clear()
    }

    @Test
    fun `resume without a pause does not open a second connection`() = runTest {
        val support = CountingSupport()
        val vm = SupportChatViewModel(support, dispatcher = main())
        vm.resume()
        assertEquals(1, support.opened)
        vm.clear()
    }

    @Test
    fun `the home sections load side by side`() = runTest {
        val vm = TodayViewModel(SlowPlayer(), main())
        vm.onNoPosition()
        advanceTimeBy(SlowPlayer.LATENCY_MS + 1)
        val home = vm.home.value
        assertEquals(1, home.unreadNotifications)
        assertEquals(1, home.suggestedChallenges.size)
        assertEquals(1, home.suggestedOsirians.size)
        assertEquals(1, home.feedPosts.size)
        vm.clear()
    }

    @Test
    fun `a refresh of the shown home screen is flagged until everything is back`() = runTest {
        val vm = TodayViewModel(SlowPlayer(), main())
        vm.onNoPosition()
        assertFalse(vm.home.value.refreshing) // the first load shows the skeleton instead
        advanceTimeBy(SlowPlayer.LATENCY_MS + 1)
        vm.refresh()
        assertTrue(vm.home.value.refreshing)
        advanceTimeBy(SlowPlayer.LATENCY_MS + 1)
        assertFalse(vm.home.value.refreshing)
        vm.clear()
    }

    @Test
    fun `the home feed pages by offset until a short page, without repeating posts`() = runTest {
        val page = TodayViewModel.FEED_PAGE
        val player = FakePlayer().apply { feed = (1..page + 3).map { FeedPost(id = it, userId = 42) } }
        val vm = TodayViewModel(player, main())
        vm.onNoPosition()
        assertEquals(page, vm.home.value.feedPosts.size)
        assertFalse(vm.home.value.feedEnd)

        // A post published elsewhere shifts the offsets, so the next page starts with a post already shown.
        player.feed = listOf(FeedPost(id = 99, userId = 42)) + player.feed
        vm.loadMoreFeed()
        assertEquals((1..page + 3).toList(), vm.home.value.feedPosts.map { it.id })
        assertTrue(vm.home.value.feedEnd)

        vm.loadMoreFeed()
        assertEquals(listOf(0, page), player.feedOffsets)
        vm.clear()
    }

    @Test
    fun `a workout import runs once at a time, reports the count and reloads progress`() = runTest {
        val training = FakeTraining()
        val vm = ProgressViewModel(training, main())
        assertEquals(mapOf("run" to "Run", "pushup" to "Push-up"), vm.state.value.names)
        val gate = CompletableDeferred<Outcome<Int>>()
        var started = 0
        val import: suspend () -> Outcome<Int> = {
            started++
            gate.await()
        }
        vm.importWorkouts(import)
        vm.importWorkouts(import)
        assertEquals(1, started)
        assertTrue(vm.state.value.importing)
        val loads = training.sessionQueries.size
        gate.complete(Outcome.Success(2))
        assertFalse(vm.state.value.importing)
        assertEquals("Imported 2 workout(s).", vm.state.value.importStatus)
        assertEquals(loads + 1, training.sessionQueries.size)

        vm.importWorkouts { Outcome.Failure(AppError.Offline()) }
        assertEquals(AppError.Offline().userMessage, vm.state.value.importStatus)
        vm.importUnavailable("Health Connect access was not allowed.")
        assertEquals("Health Connect access was not allowed.", vm.state.value.importStatus)
        vm.clear()
    }
}
