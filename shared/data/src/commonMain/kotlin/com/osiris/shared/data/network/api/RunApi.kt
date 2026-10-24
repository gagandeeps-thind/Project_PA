package com.osiris.shared.data.network.api

import com.osiris.shared.data.network.ApiClient
import com.osiris.shared.domain.model.RoutePoint
import com.osiris.shared.domain.model.RunRecord
import com.osiris.shared.domain.model.RunResult
import kotlin.time.Instant
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.JsonObject

/** Verified running: create, start, stream points, finish. */
class RunApi(private val api: ApiClient) {
    suspend fun create(startedAt: Instant, activityType: String = "run"): RunRecord =
        api.post("/api/v2/runs", ApiClient.body("activity_type" to activityType, "device_started_at" to startedAt.toString()))

    suspend fun start(runId: Int, startedAt: Instant) {
        api.post<JsonObject>("/api/v2/runs/$runId/start", ApiClient.body("device_started_at" to startedAt.toString()))
    }

    /** Appends points in sequence order. The server answers 409 when a sequence is out of order. */
    suspend fun appendPoints(runId: Int, points: List<RoutePoint>) {
        val encoded = api.json.encodeToJsonElement(ListSerializer(RoutePoint.serializer()), points)
        api.post<JsonObject>("/api/v2/runs/$runId/points", ApiClient.body("points" to encoded))
    }

    /**
     * Idempotent per [idempotencyKey]; a retry returns the first result. [autoPauseMps] is the stop speed
     * the server applies to moving time (0: auto-pause off), so its figure matches the app's.
     */
    suspend fun finish(runId: Int, finishedAt: Instant, idempotencyKey: String, autoPauseMps: Double): RunResult =
        api.post(
            "/api/v2/runs/$runId/finish",
            ApiClient.body(
                "device_finished_at" to finishedAt.toString(),
                "idempotency_key" to idempotencyKey,
                "auto_pause_mps" to autoPauseMps,
            ),
        )

    suspend fun run(runId: Int): RunRecord = api.get("/api/v2/runs/$runId")
}
