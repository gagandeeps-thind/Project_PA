package com.osiris.shared.presentation

import com.osiris.shared.core.error.AppError
import com.osiris.shared.domain.model.SupportMessage
import com.osiris.shared.domain.repository.SupportChatRepository
import com.osiris.shared.presentation.support.SupportChatState.Status
import com.osiris.shared.presentation.support.SupportChatViewModel
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlin.time.Instant
import kotlinx.coroutines.channels.ReceiveChannel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runTest

/** Greets, answers each sent text, and can be told to fail the next connection. */
private class FakeSupport : SupportChatRepository {
    val sent = mutableListOf<String>()
    var failNext = false
    override fun open(outgoing: ReceiveChannel<String>): Flow<SupportMessage> = flow {
        if (failNext) {
            failNext = false
            throw AppError.Offline()
        }
        emit(SupportMessage("support", "Hi", Instant.parse("2026-10-19T15:00:00Z")))
        for (text in outgoing) {
            sent += text
            emit(SupportMessage("support", "Thanks", Instant.parse("2026-10-19T15:01:00Z")))
        }
    }
}

class SupportChatViewModelTest {
    private fun TestScope.main() = UnconfinedTestDispatcher(testScheduler)

    @Test
    fun `chat opens on the greeting, sends trimmed text and refuses empty or oversized text`() = runTest {
        val support = FakeSupport()
        val vm = SupportChatViewModel(support, FixedClock(Instant.parse("2026-10-19T15:00:30Z")), main())
        assertEquals(Status.OPEN, vm.state.value.status)
        assertTrue(vm.send("  run not counted  "))
        assertFalse(vm.send("   "))
        assertFalse(vm.send("x".repeat(1001)))
        assertEquals(listOf("run not counted"), support.sent)
        assertEquals(listOf(false to "Hi", true to "run not counted", false to "Thanks"), vm.state.value.lines.map { it.mine to it.text })
        vm.clear()
    }

    @Test
    fun `a failed connection closes with the reason and reconnecting recovers`() = runTest {
        val support = FakeSupport().apply { failNext = true }
        val vm = SupportChatViewModel(support, dispatcher = main())
        assertEquals(Status.CLOSED, vm.state.value.status)
        assertEquals(AppError.Offline().userMessage, vm.state.value.error)
        assertFalse(vm.send("hello"))
        vm.connect()
        assertEquals(Status.OPEN, vm.state.value.status)
        assertEquals(null, vm.state.value.error)
        vm.clear()
    }
}
