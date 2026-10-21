package com.osiris.shared.data.network.api

import com.osiris.shared.data.network.ApiClient
import com.osiris.shared.domain.model.ChallengeSummary
import com.osiris.shared.domain.model.Community
import com.osiris.shared.domain.model.GlobalBoard
import com.osiris.shared.domain.model.Leaderboard
import com.osiris.shared.domain.model.SeasonLeaderboard
import com.osiris.shared.domain.model.Season
import io.ktor.http.HttpMethod
import io.ktor.http.encodeURLPathPart

/** Communities, local rankings and seasons. */
class CommunityApi(private val api: ApiClient) {
    suspend fun discover(city: String?): List<Community> = api.get("/api/v2/communities", mapOf("city" to city))

    suspend fun mine(): List<Community> = api.get("/api/v2/me/communities")

    suspend fun community(slug: String): Community = api.get("/api/v2/communities/${slug.encoded()}")

    suspend fun join(slug: String, joinCode: String?): Community =
        api.post(
            "/api/v2/communities/${slug.encoded()}/join",
            ApiClient.body("join_code" to joinCode?.trim()?.takeIf { it.isNotEmpty() }),
        )

    suspend fun leave(slug: String) = api.execute(HttpMethod.Post, "/api/v2/communities/${slug.encoded()}/leave")

    suspend fun leaderboard(slug: String): Leaderboard = api.get("/api/v2/communities/${slug.encoded()}/leaderboard")

    suspend fun challenges(slug: String): List<ChallengeSummary> =
        api.get("/api/v2/communities/${slug.encoded()}/challenges")

    suspend fun local(): Leaderboard = api.get("/api/v2/leaderboards/local")

    suspend fun globalBoard(board: String, period: String, exercise: String): GlobalBoard =
        api.get("/api/v2/leaderboards/global", mapOf("board" to board, "period" to period, "exercise" to exercise))

    suspend fun seasons(): List<Season> = api.get("/api/v2/seasons")

    suspend fun joinSeason(slug: String) = api.execute(HttpMethod.Post, "/api/v2/seasons/${slug.encoded()}/join")

    suspend fun seasonLeaderboard(slug: String): SeasonLeaderboard = api.get("/api/v2/seasons/${slug.encoded()}/leaderboard")
}

/** Slugs are typed by players (join by slug); keep them inside one path segment. */
internal fun String.encoded(): String = trim().encodeURLPathPart()
