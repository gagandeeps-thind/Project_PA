package com.osiris.shared.data

import com.osiris.shared.domain.run.AutoPause
import com.osiris.shared.domain.run.Sport
import com.osiris.shared.core.error.AppError
import com.osiris.shared.data.FakeServer.Companion.reply
import com.osiris.shared.domain.run.LocationFix
import java.util.concurrent.CountDownLatch
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlin.time.Duration.Companion.seconds
import kotlin.time.Instant
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

class RunRepositoryTest {
    private val t0 = Instant.parse("2026-05-01T06:00:00Z")

    /** Server that stores points and enforces contiguous sequences like the backend. */
    private class RunServer(val app: TestApp) {
        var stored = 0
        var dropResponses = 0

        /** When set, a points upload signals [uploading] and waits for [release]. */
        var hold = false
        val uploading = CountDownLatch(1)
        val release = CountDownLatch(1)

        init {
            app.server.json("POST /api/v1/auth/login") { """{"access_token":"t","role":"player","id":7}""" }
            app.server.json("GET /api/v1/users/7") { PLAYER }
            app.server.json("POST /api/v2/runs") { """{"id":11}""" }
            app.server.json("POST /api/v2/runs/11/start") { "{}" }
            app.server.on("GET /api/v2/runs/11") { reply(200, """{"id":11,"point_count":$stored}""") }
            app.server.on("POST /api/v2/runs/11/points") { call ->
                if (hold) {
                    hold = false
                    uploading.countDown()
                    release.await()
                }
                val points = call.body!!.jsonObject["points"]!!.jsonArray
                val first = points.first().jsonObject["sequence"]!!.jsonPrimitive.int
                if (first != stored) return@on reply(409, """{"detail":{"code":"SEQUENCE_GAP","message":"gap"}}""")
                stored += points.size
                if (dropResponses > 0) {
                    dropResponses--
                    throw java.io.IOException("response lost")
                }
                reply(200, """{"accepted":${points.size}}""")
            }
            app.server.json("POST /api/v2/runs/11/finish") {
                """{"verification_status":"accepted","distance_m":1000,"duration_seconds":300,"xp_awarded":50}"""
            }
        }
    }

    private suspend fun signedIn(app: TestApp = TestApp()): Pair<TestApp, RunServer> {
        val server = RunServer(app)
        app.graph.auth.login("p@x.io", "secret123").getOrThrow()
        return app to server
    }

    private suspend fun TestApp.walk(fixes: Int) {
        // Carry on from the last point: fixes not after it are dropped, as the server requires.
        val done = graph.runs.active.value?.nextSequence ?: 0
        repeat(fixes) { i ->
            val n = done + i
            graph.runs.addFix(LocationFix(52.0 + n * 0.0001, 4.0), t0 + (n + 1).seconds)
        }
    }

    @Test
    fun `points upload in order once five are queued`() = test {
        val (app, server) = signedIn()
        app.graph.runs.start(null, t0).getOrThrow()
        app.walk(4)
        assertEquals(0, server.stored)
        app.walk(1)
        assertEquals(5, server.stored)
        assertTrue(app.graph.runs.active.value!!.pending.isEmpty())
    }

    @Test
    fun `offline keeps every point, survives a restart, and uploads once back`() = test {
        val (app, server) = signedIn()
        app.graph.runs.start(null, t0).getOrThrow()
        app.server.offline = true
        app.walk(12)
        assertTrue(app.graph.runs.offline.value)
        assertEquals(12, app.graph.runs.active.value!!.pending.size)

        val restarted = TestApp(server = app.server, settings = app.settings, secure = app.secure)
        restarted.graph.auth.restore()
        assertEquals(12, restarted.graph.runs.active.value?.pending?.size)
        app.server.offline = false
        assertTrue(restarted.graph.runs.flush().getOrThrow())
        assertEquals(12, server.stored)
        assertFalse(restarted.graph.runs.offline.value)
    }

    @Test
    fun `a lost response is recovered from the server's point count without duplicates`() = test {
        val (app, server) = signedIn()
        app.graph.runs.start(null, t0).getOrThrow()
        server.dropResponses = 1
        app.walk(5) // stored by the server, but the phone never hears back
        assertEquals(5, server.stored)
        assertEquals(5, app.graph.runs.active.value!!.pending.size)
        app.walk(1)
        assertEquals(6, server.stored)
        assertTrue(app.graph.runs.active.value!!.pending.isEmpty())
    }

    @Test
    fun `large queues upload in batches of 400`() = test {
        val (app, server) = signedIn()
        app.graph.runs.start(null, t0).getOrThrow()
        app.server.offline = true
        app.walk(900)
        app.server.offline = false
        app.server.calls.clear()
        assertTrue(app.graph.runs.flush().getOrThrow())
        assertEquals(900, server.stored)
        assertEquals(3, app.server.count("POST /api/v2/runs/11/points"))
    }

    @Test
    fun `finishing offline keeps the run and says so`() = test {
        val (app, _) = signedIn()
        app.graph.runs.start(null, t0).getOrThrow()
        app.server.offline = true
        app.walk(3)
        assertIs<AppError.Offline>(app.graph.runs.finish(t0 + 60.seconds).errorOrNull())
        assertNotNull(app.graph.runs.active.value)
    }

    @Test
    fun `finishing during a background upload waits for it instead of reporting offline`() = test {
        val (app, server) = signedIn()
        app.graph.runs.start(null, t0).getOrThrow()
        app.walk(4)
        server.hold = true
        coroutineScope {
            // The fifth fix starts a background upload, which the server holds open.
            val background = async(Dispatchers.IO) { app.walk(1) }
            server.uploading.await()
            val finish = async(Dispatchers.IO) { app.graph.runs.finish(t0 + 60.seconds) }
            delay(200)
            server.release.countDown()
            background.await()
            assertTrue(finish.await().getOrThrow().accepted)
        }
        assertEquals(5, server.stored)
        assertNull(app.graph.runs.active.value)
    }

    @Test
    fun `finishing uploads the rest, uses a stable idempotency key, and clears the run`() = test {
        val (app, server) = signedIn()
        app.graph.runs.start(null, t0).getOrThrow()
        app.walk(3)
        val result = app.graph.runs.finish(t0 + 60.seconds).getOrThrow()
        assertTrue(result.accepted)
        assertEquals(3, server.stored)
        val body = app.server.calls.last().body!!.jsonObject
        assertEquals("run-11-finish", body["idempotency_key"]!!.jsonPrimitive.content)
        assertEquals("0.5", body["auto_pause_mps"]!!.jsonPrimitive.content) // the default, as the server's
        assertNull(app.graph.runs.active.value)
    }

    @Test
    fun `the chosen auto-pause speed reaches the server with the finish, and off sends zero`() = test {
        val (app, _) = signedIn()
        val run = app.graph.runs.start(null, t0, Sport.RUN, autoPause = AutoPause.WALKING).getOrThrow()
        assertEquals(1.5, run.autoPauseMps)
        app.walk(3)
        app.graph.runs.finish(t0 + 60.seconds).getOrThrow()
        val walking = app.server.calls.last().body!!.jsonObject
        assertEquals("1.5", walking["auto_pause_mps"]!!.jsonPrimitive.content)
        app.graph.runs.start(null, t0 + 120.seconds, Sport.RUN, autoPause = AutoPause.OFF).getOrThrow()
        app.walk(3)
        app.graph.runs.finish(t0 + 180.seconds).getOrThrow()
        assertEquals("0.0", app.server.calls.last().body!!.jsonObject["auto_pause_mps"]!!.jsonPrimitive.content)
    }

    @Test
    fun `another account never inherits someone else's unfinished run`() = test {
        val (app, _) = signedIn()
        app.graph.runs.start(null, t0).getOrThrow()
        app.server.offline = true
        app.walk(2)
        app.server.offline = false
        val other = TestApp(server = app.server, settings = app.settings)
        app.server.json("POST /api/v1/auth/login") { """{"access_token":"t2","role":"player","id":8}""" }
        app.server.json("GET /api/v1/users/8") { """{"id":8,"role":"player"}""" }
        assertNotNull(other.graph.runs.active.value)
        other.graph.auth.login("q@x.io", "secret123").getOrThrow()
        assertNull(other.graph.runs.active.value)
    }

    @Test
    fun `an unreadable saved run is discarded instead of crashing`() = test {
        val settings = com.russhwolf.settings.MapSettings()
        settings.putString("osiris.active_run.v1", "{not json")
        val app = TestApp(settings = settings)
        assertNull(app.graph.runs.active.value)
        assertNull(app.settings.getStringOrNull("osiris.active_run.v1"))
    }

    @Test
    fun `the chosen sport and auto-pause are recorded and the sport reaches the server`() = test {
        val (app, _) = signedIn()
        app.server.calls.clear()
        val run = app.graph.runs.start(null, t0, Sport.HIKE, autoPause = AutoPause.OFF).getOrThrow()
        assertEquals("hike", run.sport)
        assertEquals(false, run.autoPause)
        val create = app.server.calls.first { it.method == "POST" && it.path == "/api/v2/runs" }
        assertEquals("hike", create.body!!.jsonObject["activity_type"]!!.jsonPrimitive.content)
    }
}
