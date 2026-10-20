package com.osiris.shared.presentation.today

import com.osiris.shared.domain.model.TodayData
import com.osiris.shared.domain.repository.PlayerRepository
import com.osiris.shared.domain.run.LatLng
import com.osiris.shared.presentation.common.Loadable
import com.osiris.shared.presentation.common.SharedViewModel
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/** Home screen: today's quest, the week, tomorrow, and one nearby starter challenge. */
class TodayViewModel(
    private val player: PlayerRepository,
    dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
) : SharedViewModel(dispatcher) {
    private val _state = MutableStateFlow<Loadable<TodayData>>(Loadable.Loading)
    val state: StateFlow<Loadable<TodayData>> = _state.asStateFlow()

    /** Used only to suggest a nearby starter challenge; never stored. */
    private var position: LatLng? = null
    private var loading: Job? = null

    /** The first load waits briefly for a position, so opening the app asks for Today once, not twice. */
    private val firstPosition = CompletableDeferred<LatLng?>()

    init {
        scope.launch { player.track("app_opened") }
        loading = scope.launch {
            position = withTimeoutOrNull(POSITION_GRACE_MS) { firstPosition.await() }
            firstPosition.complete(null)
            load()
        }
    }

    /** The platform reports one position when it has one; without it only the suggestion is skipped. */
    fun onPosition(position: LatLng) {
        if (firstPosition.complete(position)) return
        if (this.position == position) return
        this.position = position
        refresh()
    }

    /** No permission or no fix: the first load need not wait for one. */
    fun onNoPosition() {
        firstPosition.complete(null)
    }

    fun refresh() {
        firstPosition.complete(null)
        loading?.cancel()
        if (_state.value !is Loadable.Ready) _state.value = Loadable.Loading
        loading = scope.launch { load() }
    }

    private suspend fun load() {
        val result = player.today(position)
        // A failed background refresh keeps the screen the player is looking at.
        val current = _state.value
        _state.value = if (result.isSuccess || current !is Loadable.Ready) Loadable.of(result) else current.also {
            result.errorOrNull()?.let(::showError)
        }
    }

    fun grantLocationConsent() {
        scope.launch {
            player.updateProfile(buildJsonObject { put("location_consent", JsonPrimitive(true)) }).orShow() ?: return@launch
            refresh()
        }
    }

    fun onStartQuest() {
        scope.launch { player.track("run_started", mapOf("source" to "today")) }
    }

    companion object {
        /** A cached or network fix usually arrives well inside this; after it Today loads without one. */
        const val POSITION_GRACE_MS = 1_000L
    }
}
