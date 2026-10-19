package com.osiris.shared.data.network

import com.osiris.shared.core.error.AppError
import io.ktor.client.network.sockets.ConnectTimeoutException
import io.ktor.client.network.sockets.SocketTimeoutException
import io.ktor.client.plugins.HttpRequestTimeoutException
import kotlinx.io.IOException
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonPrimitive

/** Maps transport failures and error responses to [AppError], with player-safe messages. */
internal object NetworkErrors {

    fun fromThrowable(e: Throwable): AppError = when (e) {
        is AppError -> e
        is HttpRequestTimeoutException, is ConnectTimeoutException, is SocketTimeoutException -> AppError.Timeout(e)
        is IOException -> AppError.Offline(e)
        else -> if (isPlatformNetworkError(e)) AppError.Offline(e) else AppError.Unexpected(e)
    }

    /** Engine-specific connection failures that are not kotlinx-io exceptions (e.g. Darwin NSURLError). */
    private fun isPlatformNetworkError(e: Throwable): Boolean {
        val name = e::class.simpleName.orEmpty()
        return name.contains("Darwin", ignoreCase = true) || name.contains("UnresolvedAddress") ||
            name.contains("ConnectException") || name.contains("UnknownHost")
    }

    /**
     * Same precedence as the Flutter client: a v2 structured detail (`{"code","message"}`), a
     * string detail, `message` / `error` fields, FastAPI validation lists, then per-status defaults.
     */
    fun fromResponse(status: Int, body: String, json: Json): AppError {
        val parsed: JsonElement? = runCatching { json.parseToJsonElement(body) }.getOrNull()
        var code: String? = null
        var detail: String? = null
        when (parsed) {
            is JsonObject -> {
                when (val raw = parsed["detail"]) {
                    is JsonPrimitive -> detail = raw.contentOrNull
                    is JsonObject -> {
                        code = raw["code"]?.stringOrNull()
                        detail = raw["message"]?.stringOrNull() ?: code
                    }
                    is JsonArray -> detail = raw.joinToString("; ") { item ->
                        (item as? JsonObject)?.get("msg")?.stringOrNull() ?: item.toString()
                    }
                    else -> Unit
                }
                if (detail == null) detail = parsed["message"]?.stringOrNull() ?: parsed["error"]?.stringOrNull()
            }
            is JsonPrimitive -> detail = parsed.contentOrNull
            else -> if (body.isNotBlank() && body.length < 300) detail = body
        }
        return when (status) {
            401 -> AppError.Unauthorized(detail ?: "Your session has expired. Please sign in again.", code)
            403 -> AppError.Http(status, code, detail ?: "Access denied. You do not have permission.")
            409 -> AppError.Http(status, code, detail ?: "Conflict. This resource already exists.")
            422 -> AppError.Http(status, code, detail ?: "Invalid input. Please check your data.")
            429 -> AppError.Http(status, code, detail ?: "Too many requests. Please wait a moment and try again.")
            in 500..599 -> AppError.Http(status, code, "Server error. Please try again later.")
            else -> AppError.Http(status, code, detail ?: "Request failed (status $status).")
        }
    }

    private fun JsonElement.stringOrNull(): String? = (this as? JsonPrimitive)?.takeIf { it.isString }?.content
        ?: (this as? JsonPrimitive)?.jsonPrimitive?.contentOrNull
}
