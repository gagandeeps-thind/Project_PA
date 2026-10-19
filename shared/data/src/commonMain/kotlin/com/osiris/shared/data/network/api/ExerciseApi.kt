package com.osiris.shared.data.network.api

import com.osiris.shared.data.network.ApiClient
import com.osiris.shared.domain.model.ConsentState
import com.osiris.shared.domain.model.ExerciseHistoryResponse
import com.osiris.shared.domain.model.ExerciseUpload
import com.osiris.shared.domain.model.ExerciseUploadResult
import kotlinx.serialization.json.JsonObject

/** Camera-verified exercises: catalog, consent, set uploads. */
class ExerciseApi(private val api: ApiClient) {
    /** The raw catalog document; parsed by the caller so the exact text can be cached. */
    suspend fun catalog(): JsonObject = api.get("/api/v2/exercises")

    /** Idempotent per `client_session_id`; a retry returns 200 with the first result. */
    suspend fun submit(upload: ExerciseUpload): ExerciseUploadResult =
        api.postBody<ExerciseUpload, ExerciseUploadResult>("/api/v2/exercise-sessions", upload)

    suspend fun consent(): ConsentState = api.get("/api/v2/me/exercise-consent")

    suspend fun setConsent(granted: Boolean, deleteData: Boolean): ConsentState =
        api.put("/api/v2/me/exercise-consent", ApiClient.body("granted" to granted, "delete_data" to deleteData))

    suspend fun history(limit: Int = 50): ExerciseHistoryResponse =
        api.get("/api/v2/me/exercise-sessions", mapOf("limit" to limit))
}
