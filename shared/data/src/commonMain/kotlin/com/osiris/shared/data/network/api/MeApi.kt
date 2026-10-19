package com.osiris.shared.data.network.api

import com.osiris.shared.data.network.ApiClient
import com.osiris.shared.domain.model.BlockEntry
import com.osiris.shared.domain.model.PlayerProfile
import com.osiris.shared.domain.model.Progression
import com.osiris.shared.domain.model.ReferralSummary
import com.osiris.shared.domain.model.ShareCard
import com.osiris.shared.domain.model.TodayData
import io.ktor.http.HttpMethod
import kotlinx.serialization.json.JsonObject

/** The signed-in player: home screen, profile, progress, growth, privacy. */
class MeApi(private val api: ApiClient) {
    suspend fun today(lat: Double?, lng: Double?, utcOffsetMinutes: Int): TodayData =
        api.get("/api/v2/me/today", mapOf("lat" to lat, "lng" to lng, "utc_offset_minutes" to utcOffsetMinutes))

    suspend fun profile(): PlayerProfile = api.get("/api/v2/me/profile")

    suspend fun updateProfile(changes: JsonObject): PlayerProfile = api.put("/api/v2/me/profile", changes)

    suspend fun progression(): Progression = api.get("/api/v2/me/progression")

    suspend fun referrals(): ReferralSummary = api.get("/api/v2/me/referrals")

    suspend fun share(kind: String, entityId: Int): ShareCard =
        api.post("/api/v2/share", ApiClient.body("kind" to kind, "entity_id" to entityId))

    suspend fun track(event: String, installId: String?, properties: Map<String, String>) =
        api.execute(
            HttpMethod.Post,
            "/api/v2/events",
            ApiClient.body("event_name" to event, "install_id" to installId, "properties" to properties),
        )

    suspend fun blocks(): List<BlockEntry> = api.get("/api/v2/me/blocks")

    suspend fun unblock(blockId: Int) = api.execute(HttpMethod.Delete, "/api/v2/blocks/$blockId")

    suspend fun export(): JsonObject = api.get("/api/v2/me/export")

    suspend fun erase(password: String) =
        api.execute(HttpMethod.Post, "/api/v2/me/erase", ApiClient.body("password" to password, "confirm" to "DELETE"))

    suspend fun rules(): JsonObject = api.get("/api/v2/rules")
}
