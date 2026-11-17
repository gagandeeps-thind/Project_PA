package com.osiris.shared.data

import com.osiris.shared.core.error.AppError
import com.osiris.shared.core.logging.Logger
import com.osiris.shared.data.FakeServer.Companion.reply
import com.osiris.shared.data.network.ApiClient
import com.osiris.shared.data.network.BoundedCacheStorage
import io.ktor.client.plugins.cache.storage.CachedResponseData
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpProtocolVersion
import io.ktor.http.HttpStatusCode
import io.ktor.http.Url
import io.ktor.http.headersOf
import io.ktor.util.date.GMTDate
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonPrimitive

class ApiClientCacheTest {
    @Test
    fun anUnchangedResponseIsRevalidatedAndServedFromTheCache() = test {
        val sentTags = mutableListOf<String?>()
        val engine = MockEngine { request ->
            val tag = request.headers[HttpHeaders.IfNoneMatch]
            sentTags += tag
            if (tag == "W/\"v1\"") {
                // Like the backend, the 304 repeats Cache-Control: Ktor picks the private store from it.
                respond(
                    "",
                    HttpStatusCode.NotModified,
                    headersOf(
                        HttpHeaders.ETag to listOf("W/\"v1\""),
                        HttpHeaders.CacheControl to listOf("private, no-cache"),
                    ),
                )
            } else {
                respond(
                    """{"xp":120}""",
                    HttpStatusCode.OK,
                    headersOf(
                        HttpHeaders.ContentType to listOf("application/json"),
                        HttpHeaders.ETag to listOf("W/\"v1\""),
                        HttpHeaders.CacheControl to listOf("private, no-cache"),
                    ),
                )
            }
        }
        val api = ApiClient(testConfig, engine, { "token" }, Logger.None)

        val first: JsonObject = api.get("api/v2/me/today")
        val second: JsonObject = api.get("api/v2/me/today")

        assertEquals(listOf(null, "W/\"v1\""), sentTags)
        assertEquals("120", first["xp"]!!.jsonPrimitive.content)
        assertEquals(first, second)

        // An account change empties the cache: the next request carries no validator from the last player.
        api.clearCache()
        api.get<JsonObject>("api/v2/me/today")
        assertEquals(listOf(null, "W/\"v1\"", null), sentTags)
    }

    @Test
    fun aGetThatFailsOnTheWayIsRetriedAndAPostIsNot() = test {
        val server = FakeServer()
        var failures = 2
        server.on("GET /api/v2/me/today") {
            if (failures-- > 0) reply(503, """{"detail":"restarting"}""") else reply(200, """{"xp":120}""")
        }
        server.json("POST /api/v2/runs", status = 503) { """{"detail":"restarting"}""" }
        server.json("GET /api/v2/missing", status = 500) { """{"detail":"boom"}""" }
        val api = ApiClient(testConfig, server.engine, { "token" }, Logger.None)

        assertEquals("120", api.get<JsonObject>("api/v2/me/today")["xp"]!!.jsonPrimitive.content)
        assertEquals(1 + ApiClient.GET_RETRIES, server.count("GET /api/v2/me/today"))

        assertEquals(503, (runCatching { api.post<JsonObject>("api/v2/runs") }.exceptionOrNull() as AppError.Http).status)
        assertEquals(1, server.count("POST /api/v2/runs"))

        // A plain 500 is the server's answer to this request, not a transport hiccup.
        assertEquals(500, (runCatching { api.get<JsonObject>("api/v2/missing") }.exceptionOrNull() as AppError.Http).status)
        assertEquals(1, server.count("GET /api/v2/missing"))
    }

    @Test
    fun aGetThatKeepsFailingGivesUpAfterTheRetries() = test {
        val server = FakeServer().apply { offline = true }
        val api = ApiClient(testConfig, server.engine, { "token" }, Logger.None)
        var attempts = 0
        val counting = io.ktor.client.engine.mock.MockEngine {
            attempts++
            throw java.io.IOException("network unreachable")
        }
        val failing = ApiClient(testConfig, counting, { "token" }, Logger.None)

        assertIs<AppError.Offline>(runCatching { api.get<JsonObject>("api/v2/me/today") }.exceptionOrNull())
        assertIs<AppError.Offline>(runCatching { failing.get<JsonObject>("api/v2/me/today") }.exceptionOrNull())
        assertEquals(1 + ApiClient.GET_RETRIES, attempts)
    }

    @Test
    fun theCacheStaysUnderItsByteLimitAndDropsTheOldestUrlFirst() = test {
        fun cached(path: String, bytes: Int) = CachedResponseData(
            url = Url("http://osiris.test/$path"), statusCode = HttpStatusCode.OK, requestTime = GMTDate(), responseTime = GMTDate(),
            version = HttpProtocolVersion.HTTP_1_1, expires = GMTDate(), headers = headersOf(), varyKeys = emptyMap(),
            body = ByteArray(bytes),
        )
        val storage = BoundedCacheStorage(maxBytes = 100)
        val a = cached("a", 40)
        val b = cached("b", 40)
        val c = cached("c", 40)
        storage.store(a.url, a)
        storage.store(b.url, b)
        storage.store(a.url, a) // revalidated: now newer than b
        storage.store(c.url, c)
        assertEquals(null, storage.find(b.url, emptyMap()))
        assertEquals(a, storage.find(a.url, emptyMap()))
        assertEquals(setOf(c), storage.findAll(c.url))

        val huge = cached("huge", 500)
        storage.store(huge.url, huge)
        assertEquals(null, storage.find(huge.url, emptyMap())) // larger than the whole cache: not kept

        storage.clear()
        assertEquals(emptySet(), storage.findAll(a.url))
    }
}
