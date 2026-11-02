package com.osiris.shared.data.network.api

import com.osiris.shared.data.network.ApiClient
import com.osiris.shared.domain.model.AriseRoute

/** Arise: public routes. */
class AriseApi(private val api: ApiClient) {
    suspend fun routes(lat: Double, lng: Double, radiusKm: Double): List<AriseRoute> =
        api.get("/api/v2/arise/routes", mapOf("lat" to lat, "lng" to lng, "radius_km" to radiusKm))

    suspend fun publish(runId: Int, name: String, hideEnds: Boolean): AriseRoute =
        api.post("/api/v2/arise/routes", ApiClient.body("run_session_id" to runId, "name" to name, "hide_ends" to hideEnds))
}
