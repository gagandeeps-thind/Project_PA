package com.osiris.shared.presentation.progress

import com.osiris.shared.core.error.map
import com.osiris.shared.domain.model.Progression
import com.osiris.shared.domain.repository.PlayerRepository
import com.osiris.shared.presentation.common.Loadable
import com.osiris.shared.presentation.common.SharedViewModel
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** Rank, XP to the next rank, totals and badges. */
data class ProgressSummary(val progression: Progression) {
    val rank: String get() = progression.performanceRank.uppercase()
    val toNext: String
        get() = progression.nextRankXp?.let { "${it - progression.xp} XP to next" } ?: "Top rank"
    val fraction: Double
        get() = progression.nextRankXp?.takeIf { it > 0 }?.let { (progression.xp.toDouble() / it).coerceIn(0.0, 1.0) } ?: 1.0
    val totals: String
        get() = with(progression) { "$verifiedRuns verified runs • $courses courses • $challengesWon wins • $defenses defenses" }
}

class ProgressViewModel(
    private val player: PlayerRepository,
    dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
) : SharedViewModel(dispatcher) {
    private val _state = MutableStateFlow<Loadable<ProgressSummary>>(Loadable.Loading)
    val state: StateFlow<Loadable<ProgressSummary>> = _state.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        scope.launch {
            _state.value = Loadable.of(player.progression().map(::ProgressSummary))
        }
    }
}
