package com.osiris.shared.presentation.support

import com.osiris.shared.core.error.AppError
import com.osiris.shared.domain.model.SupportOutgoing
import com.osiris.shared.domain.repository.SupportChatRepository
import com.osiris.shared.presentation.common.SharedViewModel
import kotlin.time.Clock
import kotlin.time.Instant
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.onCompletion
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class ChatLine(val mine: Boolean, val text: String, val at: Instant)

data class SupportChatState(
    val lines: List<ChatLine> = emptyList(),
    val status: Status = Status.CONNECTING,
    /** Why the chat closed, when it closed on an error. */
    val error: String? = null,
) {
    enum class Status { CONNECTING, OPEN, CLOSED }

    val canSend: Boolean get() = status == Status.OPEN
}

/**
 * The live support chat on Profile; reconnects only when the player asks. The chat counts as open
 * once the server's greeting arrives.
 */
class SupportChatViewModel(
    private val support: SupportChatRepository,
    private val clock: Clock = Clock.System,
    dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
) : SharedViewModel(dispatcher) {
    private val _state = MutableStateFlow(SupportChatState())
    val state: StateFlow<SupportChatState> = _state.asStateFlow()
    private var outgoing = Channel<String>(Channel.BUFFERED)
    private var connection: Job? = null
    private var generation = 0

    init {
        connect()
    }

    fun connect() {
        connection?.cancel()
        outgoing.close()
        outgoing = Channel(Channel.BUFFERED)
        // A cancelled connection may finish after the new one starts; only the current one reports.
        val current = ++generation
        _state.update { it.copy(status = SupportChatState.Status.CONNECTING, error = null) }
        connection = scope.launch {
            support.open(outgoing)
                .catch { e -> if (current == generation) _state.update { it.copy(error = AppError.from(e).userMessage) } }
                .onCompletion { if (current == generation) _state.update { it.copy(status = SupportChatState.Status.CLOSED) } }
                .collect { m ->
                    _state.update {
                        it.copy(status = SupportChatState.Status.OPEN, lines = it.lines + ChatLine(false, m.text, m.at))
                    }
                }
        }
    }

    /** Sends [text]; false when it is empty, too long or the chat is not open. */
    fun send(text: String): Boolean {
        val trimmed = text.trim()
        val valid = _state.value.canSend && trimmed.isNotEmpty() && trimmed.length <= SupportOutgoing.MAX_LENGTH
        if (!valid) return false
        // The line goes in first: on an immediate dispatcher the reply can arrive inside trySend.
        val line = ChatLine(true, trimmed, clock.now())
        _state.update { it.copy(lines = it.lines + line) }
        val sent = outgoing.trySend(trimmed).isSuccess
        if (!sent) _state.update { it.copy(lines = it.lines - line) }
        return sent
    }

    override fun clear() {
        outgoing.close()
        super.clear()
    }
}
