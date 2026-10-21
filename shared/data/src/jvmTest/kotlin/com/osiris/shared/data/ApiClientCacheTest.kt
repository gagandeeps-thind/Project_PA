package com.osiris.shared.data

import com.osiris.shared.core.logging.Logger
import com.osiris.shared.data.network.ApiClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import kotlin.test.Test
import kotlin.test.assertEquals
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
    }
}
