package com.osiris.shared.data

import com.osiris.shared.core.error.AppError
import com.osiris.shared.core.logging.Logger
import com.osiris.shared.data.network.ApiClient
import com.osiris.shared.data.support.SupportChatRepositoryImpl
import io.ktor.client.engine.cio.CIO as ClientCIO
import io.ktor.http.HttpHeaders
import io.ktor.server.application.install
import io.ktor.server.cio.CIO
import io.ktor.server.engine.embeddedServer
import io.ktor.server.routing.routing
import io.ktor.server.websocket.WebSockets
import io.ktor.server.websocket.webSocket
import io.ktor.websocket.CloseReason
import io.ktor.websocket.Frame
import io.ktor.websocket.close
import io.ktor.websocket.readText
import java.util.Collections
import kotlin.test.AfterTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.take
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout

/** The chat against a real WebSocket server speaking the backend's protocol (growth_support.py). */
class SupportChatTest {
    private val received: MutableList<String> = Collections.synchronizedList(mutableListOf())

    private val server = embeddedServer(CIO, port = 0) {
        install(WebSockets)
        routing {
            webSocket("/api/v2/support/ws") {
                if (call.request.headers[HttpHeaders.Authorization] != "Bearer good") {
                    close(CloseReason(CloseReason.Codes.VIOLATED_POLICY, "signed out"))
                    return@webSocket
                }
                send(Frame.Text(reply("Hi")))
                for (frame in incoming) {
                    if (frame is Frame.Text) {
                        received += frame.readText()
                        send(Frame.Text(reply("Thanks")))
                    }
                }
            }
        }
    }.start(wait = false)

    private val port = runBlocking { server.engine.resolvedConnectors().first().port }

    private fun reply(text: String) = """{"from":"support","text":"$text","at":"2026-10-19T15:00:00.123456+00:00"}"""

    private fun repository(token: String) = SupportChatRepositoryImpl(
        ApiClient(testConfig.copy(apiBaseUrl = "http://127.0.0.1:$port"), ClientCIO.create(), { token }, Logger.None),
    )

    @AfterTest
    fun stop() = server.stop(0, 0)

    @Test
    fun `sends the player's text and reads support's replies`() = runBlocking {
        val outgoing = Channel<String>(Channel.BUFFERED).apply { trySend("My run was not counted") }
        val messages = withTimeout(10_000) { repository("good").open(outgoing).take(2).toList() }
        assertEquals(listOf("Hi", "Thanks"), messages.map { it.text })
        assertEquals("""{"text":"My run was not counted"}""", received.single())
    }

    @Test
    fun `a refused chat ends the flow without messages`() = runBlocking {
        val messages = withTimeout(10_000) { repository("bad").open(Channel()).toList() }
        assertEquals(emptyList(), messages)
    }

    @Test
    fun `no server is an offline error`() = runBlocking {
        server.stop(0, 0)
        assertFailsWith<AppError> { withTimeout(10_000) { repository("good").open(Channel()).toList() } }
        Unit
    }
}
