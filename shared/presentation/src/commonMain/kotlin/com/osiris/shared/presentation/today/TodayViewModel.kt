package com.osiris.shared.presentation.today

import com.osiris.shared.domain.model.TodayData
import com.osiris.shared.domain.repository.PlayerRepository
import com.osiris.shared.domain.run.LatLng
import com.osiris.shared.presentation.common.Loadable
import com.osiris.shared.presentation.common.SharedViewModel
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
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

    init {
        scope.launch { player.track("app_opened") }
        refresh()
    }

    /** The platform reports one position when it has one; without it only the suggestion is skipped. */
    fun onPosition(position: LatLng) {
        if (this.position == position) return
        this.position = position
        refresh()
    }

    fun refresh() {
        loading?.cancel()
        if (_state.value !is Loadable.Ready) _state.value = Loadable.Loading
        loading = scope.launch {
            val result = player.today(position)
            // A failed background refresh keeps the screen the player is looking at.
            val current = _state.value
            _state.value = if (result.isSuccess || current !is Loadable.Ready) Loadable.of(result) else current.also {
                result.errorOrNull()?.let(::showError)
            }
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
}
