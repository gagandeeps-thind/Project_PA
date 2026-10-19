package com.osiris.shared.data

import com.osiris.shared.core.config.AppConfig
import com.osiris.shared.core.config.FeatureFlags
import com.osiris.shared.core.logging.Logger
import com.osiris.shared.data.storage.InMemorySecureStore
import com.osiris.shared.data.storage.JvmPlatform
import com.osiris.shared.data.storage.PlatformDependencies
import com.russhwolf.settings.MapSettings
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockRequestHandleScope
import io.ktor.client.engine.mock.respond
import io.ktor.client.engine.mock.toByteArray
import io.ktor.client.request.HttpRequestData
import io.ktor.client.request.HttpResponseData
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import java.io.IOException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement

/** A recorded request: method, path and parsed JSON body. */
data class Call(val method: String, val path: String, val body: JsonElement?, val auth: String?)

/** Scripted backend for repository tests. Routes are `"POST /api/v2/runs"`; unmatched calls answer 404. */
class FakeServer {
    val calls = mutableListOf<Call>()
    private val routes = mutableMapOf<String, MockRequestHandleScope.(Call) -> HttpResponseData>()

    /** When true, every request fails as if the phone had no network. */
    var offline = false

    fun on(route: String, handler: MockRequestHandleScope.(Call) -> HttpResponseData) {
        routes[route] = handler
    }

    fun json(route: String, status: Int = 200, body: () -> String) = on(route) { reply(status, body()) }

    fun count(route: String) = calls.count { "${it.method} ${it.path}" == route }

    val engine = MockEngine { request -> handle(request) }

    private suspend fun MockRequestHandleScope.handle(request: HttpRequestData): HttpResponseData {
        if (offline) throw IOException("network unreachable")
        val text = request.body.toByteArray().decodeToString()
        val call = Call(
            request.method.value,
            request.url.encodedPath,
            text.takeIf { it.isNotBlank() }?.let { Json.parseToJsonElement(it) },
            request.headers[HttpHeaders.Authorization],
        )
        calls += call
        val handler = routes["${call.method} ${call.path}"] ?: return reply(404, """{"detail":"not found"}""")
        return handler(call)
    }

    companion object {
        fun MockRequestHandleScope.reply(status: Int, body: String) =
            respond(body, HttpStatusCode.fromValue(status), headersOf(HttpHeaders.ContentType, "application/json"))
    }
}

val testConfig = AppConfig(
    environment = "test",
    apiBaseUrl = "http://osiris.test",
    connectTimeoutMs = 1_000,
    requestTimeoutMs = 1_000,
    httpLogging = false,
    features = FeatureFlags(legacyGame = false, poseRecording = true),
)

/** A data graph against [server], with in-memory settings, secrets and SQLite. */
class TestApp(
    val server: FakeServer = FakeServer(),
    val settings: MapSettings = MapSettings(),
    val secure: InMemorySecureStore = InMemorySecureStore(),
    dbUrl: String = "jdbc:sqlite::memory:",
    recordingsDir: String? = null,
    openDatabase: (() -> app.cash.sqldelight.db.SqlDriver)? = null,
) {
    val graph = DataGraph(
        testConfig,
        PlatformDependencies(
            settings = settings,
            secureStore = secure,
            httpEngine = server.engine,
            openDatabase = openDatabase ?: { JvmPlatform.openJvmDatabase(dbUrl) },
            logger = Logger.None,
            recordingsDir = recordingsDir,
        ),
        io = Dispatchers.IO,
    )
}

fun test(block: suspend () -> Unit) = runBlocking { block() }

const val PLAYER = """{"id":7,"email":"p@x.io","xp":120,"role":"player"}"""
