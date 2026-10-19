package com.osiris.shared.presentation.challenge

import com.osiris.shared.domain.model.ChallengeSummary
import com.osiris.shared.domain.repository.ChallengeRepository
import com.osiris.shared.domain.run.LatLng
import com.osiris.shared.presentation.common.Loadable
import com.osiris.shared.presentation.common.SharedViewModel
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class ChallengeBoardState(
    val radiusKm: Double = 5.0,
    /** Loading until the platform reports a position. */
    val challenges: Loadable<List<ChallengeSummary>> = Loadable.Loading,
) {
    val radii: List<Double> get() = RADII

    companion object {
        val RADII = listOf(2.0, 5.0, 10.0, 25.0)
    }
}

/** Open challenges near the player, within a chosen radius. */
class ChallengeBoardViewModel(
    private val challenges: ChallengeRepository,
    dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
) : SharedViewModel(dispatcher) {
    private val _state = MutableStateFlow(ChallengeBoardState())
    val state: StateFlow<ChallengeBoardState> = _state.asStateFlow()
    private var position: LatLng? = null
    private var loading: Job? = null

    fun onPosition(position: LatLng) {
        this.position = position
        refresh()
    }

    fun setRadius(km: Double) {
        _state.update { it.copy(radiusKm = km) }
        refresh()
    }

    fun refresh() {
        val at = position ?: return
        loading?.cancel()
        _state.update { it.copy(challenges = Loadable.Loading) }
        loading = scope.launch {
            val result = challenges.nearby(at, _state.value.radiusKm)
            _state.update { it.copy(challenges = Loadable.of(result)) }
        }
    }
}
