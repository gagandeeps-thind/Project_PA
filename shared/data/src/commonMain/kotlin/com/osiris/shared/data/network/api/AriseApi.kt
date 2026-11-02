package com.osiris.shared.data.network.api

import com.osiris.shared.data.network.ApiClient
import com.osiris.shared.domain.model.AriseAttackResult
import com.osiris.shared.domain.model.AriseDomain
import com.osiris.shared.domain.model.AriseDomains
import com.osiris.shared.domain.model.AriseRoute
import com.osiris.shared.domain.model.AriseWorkout
import com.osiris.shared.domain.model.AriseWorkoutResult
import com.osiris.shared.domain.model.HeatCell

/** Arise: public routes. */
class AriseApi(private val api: ApiClient) {
    suspend fun routes(lat: Double, lng: Double, radiusKm: Double): List<AriseRoute> =
        api.get("/api/v2/arise/routes", mapOf("lat" to lat, "lng" to lng, "radius_km" to radiusKm))

    suspend fun publish(runId: Int, name: String, hideEnds: Boolean): AriseRoute =
        api.post("/api/v2/arise/routes", ApiClient.body("run_session_id" to runId, "name" to name, "hide_ends" to hideEnds))

    suspend fun domains(lat: Double, lng: Double, radiusKm: Double): AriseDomains =
        api.get("/api/v2/arise/domains", mapOf("lat" to lat, "lng" to lng, "radius_km" to radiusKm))

    suspend fun claim(runId: Int): AriseDomain = api.post("/api/v2/arise/domains", ApiClient.body("run_session_id" to runId))

    suspend fun exceed(domainId: Int): AriseWorkout = api.post("/api/v2/arise/domains/$domainId/workout")

    suspend fun completeExceed(domainId: Int): AriseWorkoutResult = api.post("/api/v2/arise/domains/$domainId/workout/complete")

    suspend fun attack(domainId: Int, runId: Int): AriseAttackResult =
        api.post("/api/v2/arise/domains/$domainId/attack", ApiClient.body("run_session_id" to runId))

    suspend fun completeAttack(attackId: Int): AriseAttackResult = api.post("/api/v2/arise/attacks/$attackId/workout/complete")

    suspend fun heatmap(kind: String, south: Double, west: Double, north: Double, east: Double): List<HeatCell> =
        api.get(
            "/api/v2/arise/heatmap",
            mapOf("kind" to kind, "min_lat" to south, "min_lng" to west, "max_lat" to north, "max_lng" to east),
        )

    suspend fun photo(domainId: Int, jpegBase64: String): AriseDomain =
        api.put("/api/v2/arise/domains/$domainId/photo", ApiClient.body("jpeg_base64" to jpegBase64))
}
