package com.osiris.shared.presentation.discover

import com.osiris.shared.core.error.map
import com.osiris.shared.domain.common.Format
import com.osiris.shared.domain.model.HubChallenge
import com.osiris.shared.domain.model.HubSection
import com.osiris.shared.domain.repository.ChallengeRepository
import com.osiris.shared.presentation.common.Loadable
import com.osiris.shared.presentation.common.SharedViewModel
import kotlin.time.Clock
import kotlin.time.Duration.Companion.seconds
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** A Discover card with its two text lines already written, so both apps show the same words. */
data class DiscoverCard(val item: HubChallenge, val headline: String, val detail: String) {
    val challengeId: Int get() = item.challenge.id
}

data class DiscoverState(
    val sections: Map<HubSection, Loadable<List<DiscoverCard>>> = HubSection.entries.associateWith { Loadable.Loading },
)

/** Happening now, upcoming, community and just-finished challenges; each section loads on its own. */
class DiscoverViewModel(
    private val challenges: ChallengeRepository,
    private val clock: Clock = Clock.System,
    dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
) : SharedViewModel(dispatcher) {
    private val _state = MutableStateFlow(DiscoverState())
    val state: StateFlow<DiscoverState> = _state.asStateFlow()

    init {
        refresh()
    }

    fun refresh() = HubSection.entries.forEach(::load)

    fun load(section: HubSection) {
        scope.launch {
            val result = challenges.hub(section).map { items -> items.map { card(section, it) } }
            _state.update { it.copy(sections = it.sections + (section to Loadable.of(result))) }
        }
    }

    private fun card(section: HubSection, item: HubChallenge): DiscoverCard {
        val c = item.challenge
        val distance = Format.distance(c.courseDistanceM)
        val people = if (item.participants == 1) "1 player" else "${item.participants} players"
        val detail = when (section) {
            HubSection.LIVE -> "$distance  •  $people  •  ${c.closesIn(clock.now())}"
            HubSection.UPCOMING -> "$distance  •  starts in ${startsIn(item.startsInSeconds ?: 0)}"
            HubSection.COMMUNITY -> "${item.communityName ?: "Community"}  •  $distance  •  ${c.closesIn(clock.now())}"
            HubSection.FINISHED -> podium(item)
        }
        return DiscoverCard(item, c.title, detail)
    }

    private fun podium(item: HubChallenge): String {
        val winners = item.winners.joinToString("   ") { "${it.rank}. ${it.name} ${Format.duration(it.elapsedSeconds)}" }
        val xp = item.xpPaid?.takeIf { it > 0 }?.let { "  •  $it XP paid" }.orEmpty()
        return winners.ifEmpty { "No one beat the target" } + xp
    }

    private fun startsIn(seconds: Int): String = seconds.seconds.toComponents { days, hours, minutes, _, _ ->
        when {
            days > 0 -> "${days}d ${hours}h"
            hours > 0 -> "${hours}h ${minutes}m"
            else -> "${minutes.coerceAtLeast(1)}m"
        }
    }
}
