package com.osiris.shared.presentation.social

import com.osiris.shared.core.error.Outcome
import com.osiris.shared.domain.model.Connection
import com.osiris.shared.domain.model.DirectMessage
import com.osiris.shared.domain.model.Inbox
import com.osiris.shared.domain.model.SocialUser
import com.osiris.shared.domain.repository.SocialRepository
import com.osiris.shared.domain.repository.TrainingRepository
import com.osiris.shared.presentation.common.Loadable
import com.osiris.shared.presentation.common.SharedViewModel
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

data class InboxState(
    val inbox: Loadable<Inbox> = Loadable.Loading,
    /** Followers and people you follow: who a new message can go to. Null until the picker opens. */
    val contacts: Loadable<List<Connection>>? = null,
) {
    /** Everyone the player can write to, those they already talk to first. */
    val newMessageOptions: List<Connection>
        get() {
            val threads = inbox.valueOrNull?.items.orEmpty().map { it.user.userId }.toSet()
            return contacts?.valueOrNull.orEmpty().sortedBy { if (it.userId in threads) 0 else 1 }
        }
}

/** The direct-message inbox, newest conversation first. */
class InboxViewModel(
    private val social: SocialRepository,
    private val training: TrainingRepository,
    dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
) : SharedViewModel(dispatcher) {
    private val _state = MutableStateFlow(InboxState())
    val state: StateFlow<InboxState> = _state.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        scope.launch {
            val result = social.inbox()
            _state.update { s -> if (result is Outcome.Failure && s.inbox is Loadable.Ready) s else s.copy(inbox = Loadable.of(result)) }
        }
    }

    /** Loads who the player can write to, for the new-message picker. */
    fun openNewMessage() {
        if (_state.value.contacts is Loadable.Ready) return
        _state.update { it.copy(contacts = Loadable.Loading) }
        scope.launch {
            val result = training.connections()
            _state.update { it.copy(contacts = Loadable.of(result)) }
        }
    }
}

data class ChatState(
    val user: SocialUser? = null,
    val messages: Loadable<List<DirectMessage>> = Loadable.Loading,
    val canMessage: Boolean = false,
    val draft: String = "",
    val sending: Boolean = false,
    val loadingOlder: Boolean = false,
    val reachedStart: Boolean = false,
) {
    val canSend: Boolean get() = canMessage && draft.isNotBlank() && !sending && draft.length <= MAX_LENGTH

    companion object {
        const val MAX_LENGTH = 1000
    }
}

/**
 * One conversation. New messages arrive by polling every [pollMs] while the screen is open (0 turns
 * polling off, as tests do). Opening it marks the thread read.
 */
class ChatViewModel(
    private val userId: Int,
    private val social: SocialRepository,
    dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
    private val pollMs: Long = POLL_MS,
) : SharedViewModel(dispatcher) {
    private val _state = MutableStateFlow(ChatState())
    val state: StateFlow<ChatState> = _state.asStateFlow()

    init {
        scope.launch {
            load()
            if (pollMs > 0) {
                while (isActive) {
                    delay(pollMs)
                    load()
                }
            }
        }
    }

    /** Fetches the newest page and merges it with what is shown, keeping older pages. */
    private suspend fun load() {
        val result = social.thread(userId)
        _state.update { s ->
            when (result) {
                is Outcome.Success -> {
                    val t = result.value
                    val merged = (s.messages.valueOrNull.orEmpty() + t.items).associateBy { it.id }.values.sortedBy { it.id }
                    s.copy(user = t.user, canMessage = t.canMessage, messages = Loadable.Ready(merged))
                }
                is Outcome.Failure -> if (s.messages is Loadable.Ready) s else s.copy(messages = Loadable.failed(result.error))
            }
        }
        val incomingUnread = (result as? Outcome.Success)?.value?.items.orEmpty().any { !it.mine && !it.read }
        if (incomingUnread) social.markRead(userId)
    }

    /** Tries the thread again after a failed first load. */
    fun reload() {
        _state.update { if (it.messages is Loadable.Failed) it.copy(messages = Loadable.Loading) else it }
        scope.launch { load() }
    }

    fun edit(text: String) = _state.update { it.copy(draft = text.take(ChatState.MAX_LENGTH)) }

    fun send() {
        val s = _state.value
        if (!s.canSend) return
        val text = s.draft.trim()
        _state.update { it.copy(sending = true) }
        scope.launch {
            val sent = social.send(userId, text).orShow()
            _state.update { cur ->
                if (sent == null) return@update cur.copy(sending = false)
                cur.copy(
                    sending = false, draft = "",
                    messages = Loadable.Ready((cur.messages.valueOrNull.orEmpty() + sent).distinctBy { it.id }),
                )
            }
        }
    }

    fun loadOlder() {
        val s = _state.value
        val first = s.messages.valueOrNull?.firstOrNull()?.id ?: return
        if (s.loadingOlder || s.reachedStart) return
        _state.update { it.copy(loadingOlder = true) }
        scope.launch {
            val page = social.thread(userId, beforeId = first).orShow()
            _state.update { cur ->
                if (page == null) return@update cur.copy(loadingOlder = false)
                cur.copy(
                    loadingOlder = false, reachedStart = page.items.size < PAGE,
                    messages = Loadable.Ready((page.items + cur.messages.valueOrNull.orEmpty()).distinctBy { it.id }),
                )
            }
        }
    }

    companion object {
        const val POLL_MS = 5_000L
        private const val PAGE = 50
    }
}
