package com.osiris.shared.data.repository

import com.osiris.shared.core.error.AppError
import com.osiris.shared.core.error.Outcome
import com.osiris.shared.core.error.outcomeOf
import com.osiris.shared.data.network.api.ChallengeApi
import com.osiris.shared.data.network.api.CommunityApi
import com.osiris.shared.domain.model.ChallengeSummary
import com.osiris.shared.domain.model.Community
import com.osiris.shared.domain.model.Leaderboard
import com.osiris.shared.domain.model.SeasonLeaderboard
import com.osiris.shared.domain.model.Season
import com.osiris.shared.domain.repository.CommunityRepository

class CommunityRepositoryImpl(
    private val api: CommunityApi,
    private val reports: ChallengeApi,
) : CommunityRepository {
    override suspend fun discover(city: String?): Outcome<List<Community>> =
        outcomeOf { api.discover(city?.trim()?.takeIf { it.isNotEmpty() }) }

    override suspend fun mine(): Outcome<List<Community>> = outcomeOf { api.mine() }

    override suspend fun community(slug: String): Outcome<Community> = outcomeOf { api.community(slug) }

    override suspend fun join(slug: String, joinCode: String?): Outcome<Community> = outcomeOf {
        if (slug.isBlank()) throw AppError.Validation("Enter the community's name or link.")
        api.join(slug, joinCode)
    }

    override suspend fun leave(slug: String): Outcome<Unit> = outcomeOf { api.leave(slug) }

    override suspend fun leaderboard(slug: String): Outcome<Leaderboard> = outcomeOf { api.leaderboard(slug) }

    override suspend fun challenges(slug: String): Outcome<List<ChallengeSummary>> = outcomeOf { api.challenges(slug) }

    override suspend fun local(): Outcome<Leaderboard> = outcomeOf { api.local() }

    override suspend fun seasons(): Outcome<List<Season>> = outcomeOf { api.seasons() }

    override suspend fun joinSeason(slug: String): Outcome<Unit> = outcomeOf { api.joinSeason(slug) }

    override suspend fun seasonLeaderboard(slug: String): Outcome<SeasonLeaderboard> = outcomeOf { api.seasonLeaderboard(slug) }

    override suspend fun report(slug: String): Outcome<String> =
        outcomeOf { reports.report("community", null, slug, "spam").message }
}
