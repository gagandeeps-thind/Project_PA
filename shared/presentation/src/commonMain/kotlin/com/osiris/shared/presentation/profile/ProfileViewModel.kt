package com.osiris.shared.presentation.profile

import com.osiris.shared.core.error.Outcome
import com.osiris.shared.domain.common.Format
import com.osiris.shared.domain.model.Goal
import com.osiris.shared.domain.model.PlayerProfile
import com.osiris.shared.domain.model.Progression
import com.osiris.shared.domain.repository.PlayerRepository
import com.osiris.shared.presentation.common.Loadable
import com.osiris.shared.presentation.common.SharedViewModel
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** One tile of the profile's metrics grid. */
data class Metric(val label: String, val value: String)

/** Header, XP gauge through the current rank, metrics grid and badges. */
data class ProfileSummary(val profile: PlayerProfile, val progression: Progression) {
    val name: String get() = profile.displayName.ifBlank { "Runner" }
    val goal: String get() = Goal.entries.firstOrNull { it.wire == profile.goal }?.label.orEmpty()
    val rank: String get() = progression.performanceRank.uppercase()
    val gauge: Double get() = progression.rankFraction
    val toNext: String
        get() = progression.nextRankXp?.let { "${it - progression.xp} XP to next rank" } ?: "Top rank"
    val xp: String get() = "${progression.xp} XP"

    val metrics: List<Metric>
        get() = with(progression) {
            listOf(
                Metric("Distance", "${Format.fixed(lifetimeDistanceKm, 1)} km"),
                Metric("Verified runs", "$verifiedRuns"),
                Metric("Challenges", "$challengesPlayed"),
                Metric("Win rate", winRate?.let { "${Format.fixed(it * 100, 0)}%" } ?: "–"),
                Metric("Global rank", globalRank?.let { "#$it" } ?: "–"),
                Metric("Courses", "$courses"),
                Metric("Defenses", "$defenses"),
                Metric("Badges", "${badges.size}"),
            )
        }
}

class ProfileViewModel(
    private val player: PlayerRepository,
    dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
) : SharedViewModel(dispatcher) {
    private val _state = MutableStateFlow<Loadable<ProfileSummary>>(Loadable.Loading)
    val state: StateFlow<Loadable<ProfileSummary>> = _state.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        scope.launch {
            val profile = async { player.profile() }
            val progression = async { player.progression() }
            val p = profile.await()
            val g = progression.await()
            _state.value = when {
                p is Outcome.Failure -> Loadable.failed(p.error)
                g is Outcome.Failure -> Loadable.failed(g.error)
                else -> Loadable.Ready(ProfileSummary(p.getOrThrow(), g.getOrThrow()))
            }
        }
    }
}
