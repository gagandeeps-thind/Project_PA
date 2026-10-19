package com.osiris.shared.presentation.community

import com.osiris.shared.core.error.map
import com.osiris.shared.domain.model.Leaderboard
import com.osiris.shared.domain.model.Season
import com.osiris.shared.domain.model.SeasonLeaderboard
import com.osiris.shared.domain.repository.CommunityRepository
import com.osiris.shared.presentation.common.Loadable
import com.osiris.shared.presentation.common.SharedViewModel
import kotlin.time.Clock
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class SeasonCard(val season: Season, val board: SeasonLeaderboard?, val status: String)

data class RankingsState(
    val local: Loadable<Leaderboard> = Loadable.Loading,
    val seasons: Loadable<List<SeasonCard>> = Loadable.Loading,
)

/** This week's local leaderboard, and city seasons with their club standings. */
class RankingsViewModel(
    private val communities: CommunityRepository,
    private val clock: Clock = Clock.System,
    dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
) : SharedViewModel(dispatcher) {
    private val _state = MutableStateFlow(RankingsState())
    val state: StateFlow<RankingsState> = _state.asStateFlow()

    init {
        refreshLocal()
        refreshSeasons()
    }

    fun refreshLocal() {
        scope.launch { _state.update { it.copy(local = Loadable.of(communities.local())) } }
    }

    fun refreshSeasons() {
        scope.launch {
            val cards = communities.seasons().map { list ->
                // A season whose board does not load still shows, with its join button.
                list.map { s -> SeasonCard(s, communities.seasonLeaderboard(s.slug).getOrNull(), status(s)) }
            }
            _state.update { it.copy(seasons = Loadable.of(cards)) }
        }
    }

    fun joinSeason(slug: String) {
        scope.launch {
            communities.joinSeason(slug).orShow() ?: return@launch
            refreshSeasons()
        }
    }

    private fun status(s: Season): String {
        val daysLeft = (s.endsAt - clock.now()).inWholeDays
        val timing = if (s.status == "upcoming") "Starts soon" else "$daysLeft days left"
        return "$timing  •  ${s.participants} taking part"
    }
}
