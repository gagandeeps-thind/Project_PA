package com.osiris.shared.data.network

import com.osiris.shared.core.config.AppConfig
import com.osiris.shared.core.error.AppError
import com.osiris.shared.core.logging.Logger
import io.ktor.client.HttpClient
import io.ktor.client.engine.HttpClientEngine
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.plugins.defaultRequest
import io.ktor.client.plugins.logging.LogLevel
import io.ktor.client.plugins.logging.Logging
import io.ktor.client.plugins.websocket.DefaultClientWebSocketSession
import io.ktor.client.plugins.websocket.WebSockets
import io.ktor.client.plugins.websocket.webSocketSession
import io.ktor.client.request.HttpRequestBuilder
import io.ktor.client.request.bearerAuth
import io.ktor.client.request.parameter
import io.ktor.client.request.request
import io.ktor.client.request.setBody
import io.ktor.client.request.url
import io.ktor.client.statement.HttpResponse
import io.ktor.client.statement.bodyAsText
import io.ktor.http.ContentType
import io.ktor.http.HttpMethod
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import io.ktor.serialization.kotlinx.json.json
import io.ktor.websocket.close
import kotlin.coroutines.cancellation.CancellationException
import kotlinx.serialization.KSerializer
import kotlinx.serialization.SerializationException
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.serializer

/** Supplies the bearer token for each request; null when signed out. */
fun interface TokenProvider {
    suspend fun token(): String?
}

/**
 * The single HTTP entry point to the Osiris backend. Every call returns the decoded body or throws
 * an [AppError]; Ktor, socket and serialization exceptions never leak to callers. Repositories wrap
 * calls in `outcomeOf`, so the layers above see [com.osiris.shared.core.error.Outcome] only.
 *
 * A 401 also calls [onUnauthorized], so the session ends wherever the expired token was used.
 */
class ApiClient(
    private val config: AppConfig,
    engine: HttpClientEngine,
    private val tokens: TokenProvider,
    private val logger: Logger,
    private val onUnauthorized: suspend () -> Unit = {},
) {
    val json: Json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
        encodeDefaults = true
        coerceInputValues = true
    }

    private val http = HttpClient(engine) {
        expectSuccess = false
        install(ContentNegotiation) { json(json) }
        // Pings keep an idle chat inside the socket timeout below.
        install(WebSockets) { pingIntervalMillis = config.requestTimeoutMs / 2 }
        install(HttpTimeout) {
            connectTimeoutMillis = config.connectTimeoutMs
            requestTimeoutMillis = config.requestTimeoutMs
            socketTimeoutMillis = config.requestTimeoutMs
        }
        if (config.httpLogging) {
            install(Logging) {
                level = LogLevel.INFO
                logger = object : io.ktor.client.plugins.logging.Logger {
                    override fun log(message: String) = this@ApiClient.logger.debug(TAG, message)
                }
                // Never log credentials.
                sanitizeHeader { it.equals("Authorization", ignoreCase = true) }
            }
        }
        defaultRequest {
            url(config.apiBaseUrl + "/")
            contentType(ContentType.Application.Json)
        }
    }

    suspend inline fun <reified T> get(path: String, query: Map<String, Any?> = emptyMap()): T =
        send(HttpMethod.Get, path, query, null, serializer())

    suspend inline fun <reified T> post(path: String, body: JsonElement? = null): T =
        send(HttpMethod.Post, path, emptyMap(), body, serializer())

    suspend inline fun <reified T> put(path: String, body: JsonElement): T =
        send(HttpMethod.Put, path, emptyMap(), body, serializer())

    suspend inline fun <reified B, reified T> postBody(path: String, body: B): T =
        send(HttpMethod.Post, path, emptyMap(), json.encodeToJsonElement(serializer<B>(), body), serializer())

    /** For endpoints whose body the app does not read. */
    suspend fun execute(method: HttpMethod, path: String, body: JsonElement? = null) {
        send(method, path, emptyMap(), body, JsonElement.serializer())
    }

    suspend fun <T> send(
        method: HttpMethod,
        path: String,
        query: Map<String, Any?>,
        body: JsonElement?,
        deserializer: KSerializer<T>,
    ): T {
        val response = try {
            http.request {
                this.method = method
                url(path.trimStart('/'))
                query.forEach { (k, v) -> if (v != null) parameter(k, v) }
                if (body != null) setBody(body)
                authorize()
            }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Throwable) {
            throw NetworkErrors.fromThrowable(e)
        }
        return decode(response, deserializer)
    }

    /**
     * Opens a WebSocket on [path] (`ws://` or `wss://` matching the API's scheme) with the session
     * token, runs [block] while it is open, then closes it. Handshake failures throw an [AppError].
     */
    suspend fun <T> webSocket(path: String, block: suspend DefaultClientWebSocketSession.() -> T): T {
        val token = tokens.token()
        val session = try {
            http.webSocketSession {
                url(config.apiBaseUrl.replaceFirst("http", "ws") + "/" + path.trimStart('/'))
                token?.let { bearerAuth(it) }
            }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Throwable) {
            throw NetworkErrors.fromThrowable(e)
        }
        return try {
            session.block()
        } finally {
            session.close()
        }
    }

    private suspend fun HttpRequestBuilder.authorize() {
        tokens.token()?.let { bearerAuth(it) }
    }

    private suspend fun <T> decode(response: HttpResponse, deserializer: KSerializer<T>): T {
        val text = try {
            response.bodyAsText()
        } catch (e: CancellationException) {
            throw e
        } catch (e: Throwable) {
            throw NetworkErrors.fromThrowable(e)
        }
        if (!response.status.isSuccess()) {
            val error = NetworkErrors.fromResponse(response.status.value, text, json)
            if (error is AppError.Unauthorized) onUnauthorized()
            logger.warn(TAG, "${response.call.request.method.value} ${response.call.request.url.encodedPath} -> ${response.status.value}")
            throw error
        }
        return try {
            json.decodeFromString(deserializer, text.ifBlank { "{}" })
        } catch (e: SerializationException) {
            logger.error(TAG, "Unexpected response shape from ${response.call.request.url.encodedPath}", e)
            throw AppError.InvalidResponse(e)
        } catch (e: IllegalArgumentException) {
            throw AppError.InvalidResponse(e)
        }
    }

    fun close() = http.close()

    companion object {
        const val TAG = "OsirisApi"

        /** Builds a JSON object body without nulls (the backend treats a sent null as a value). */
        fun body(vararg pairs: Pair<String, Any?>): JsonObject = JsonBodies.of(*pairs)
    }
}
