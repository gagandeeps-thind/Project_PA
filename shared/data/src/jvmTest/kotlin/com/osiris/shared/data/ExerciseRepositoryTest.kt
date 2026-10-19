package com.osiris.shared.data

import com.osiris.shared.core.error.AppError
import com.osiris.shared.data.FakeServer.Companion.reply
import com.osiris.shared.data.storage.JvmPlatform
import com.osiris.shared.domain.exercise.PoseRecording
import com.osiris.shared.domain.exercise.RepResult
import com.osiris.shared.domain.exercise.SessionSummary
import com.osiris.shared.domain.exercise.Verdict
import com.osiris.shared.domain.model.SyncState
import java.nio.file.Files
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertTrue
import kotlin.time.Duration.Companion.minutes
import kotlin.time.Instant
import kotlinx.coroutines.delay
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

class ExerciseRepositoryTest {
    private val t0 = Instant.parse("2026-05-01T07:00:00Z")

    private fun summary(key: String = "squat", valid: Int = 3, verdict: Verdict = Verdict.VERIFIED, holdS: Double = 0.0) =
        SessionSummary(
            exerciseKey = key,
            rulesVersion = "2026.05.1",
            durationS = 30.0,
            repsAttempted = valid + 1,
            repsValid = valid,
            holdS = holdS,
            formScore = 0.9,
            verdict = verdict,
            reasons = if (verdict == Verdict.VERIFIED) emptyList() else listOf("too_fast"),
            reps = (0..valid).map { i -> RepResult(i, i * 2000L, 1500L + i, 95.0, valid = i < valid) },
        )

    /** Signs in player [id] with exercise endpoints that accept every upload. */
    private suspend fun signedIn(app: TestApp = TestApp(), id: Int = 7, status: Int = 200): TestApp {
        app.server.json("POST /api/v1/auth/login") { """{"access_token":"t$id","role":"player","id":$id}""" }
        app.server.json("GET /api/v1/users/$id") { """{"id":$id,"role":"player"}""" }
        app.server.on("POST /api/v2/exercise-sessions") { reply(status, """{"status":"verified","xp_awarded":15}""") }
        app.server.json("GET /api/v2/me/exercise-sessions") { """{"sessions":[]}""" }
        app.graph.auth.login("p@x.io", "secret123").getOrThrow()
        return app
    }

    @Test
    fun `a saved set uploads with its valid rep timings and earns XP`() = test {
        val app = signedIn()
        val out = app.graph.exercises.saveSet(summary(), t0).getOrThrow()
        assertTrue(out.uploaded)
        assertEquals(15, out.xpAwarded)
        val body = app.server.calls.last { it.path == "/api/v2/exercise-sessions" }.body!!.jsonObject
        assertEquals("[1.5,1.501,1.502]", body["rep_durations_s"].toString())
        assertEquals("verified", body["client_verdict"]!!.jsonPrimitive.content)
        val stored = app.graph.exercises.history().recent.single()
        assertEquals(SyncState.SYNCED, stored.syncState)
        assertEquals(listOf(1.5, 1.501, 1.502), stored.repDurationsS)
    }

    @Test
    fun `offline keeps the set pending and a later sync uploads it once`() = test {
        val app = signedIn()
        app.server.offline = true
        val out = app.graph.exercises.saveSet(summary(), t0).getOrThrow()
        assertFalse(out.uploaded)
        assertEquals(SyncState.PENDING, app.graph.exercises.history().recent.single().syncState)
        app.server.offline = false
        assertTrue(app.graph.exercises.sync())
        assertFalse(app.graph.exercises.sync())
        assertEquals(1, app.server.count("POST /api/v2/exercise-sessions"))
    }

    @Test
    fun `a 422 stops retrying the set, a 503 keeps it for later`() = test {
        val refused = signedIn(status = 422)
        refused.graph.exercises.saveSet(summary(), t0).getOrThrow()
        assertEquals(SyncState.FAILED, refused.graph.exercises.history().recent.single().syncState)

        val busy = signedIn(status = 503)
        busy.graph.exercises.saveSet(summary(), t0).getOrThrow()
        assertEquals(SyncState.PENDING, busy.graph.exercises.history().recent.single().syncState)
    }

    @Test
    fun `personal bests count only verified sets, per exercise`() = test {
        val app = signedIn()
        app.graph.exercises.saveSet(summary(valid = 5), t0).getOrThrow()
        app.graph.exercises.saveSet(summary(valid = 9, verdict = Verdict.REJECTED), t0 + 1.minutes).getOrThrow()
        app.graph.exercises.saveSet(summary(key = "plank", valid = 0, holdS = 42.5), t0 + 2.minutes).getOrThrow()
        assertEquals(mapOf("squat" to 5.0, "plank" to 42.5), app.graph.exercises.history().bests)
    }

    @Test
    fun `review outcomes reach sets already uploaded`() = test {
        val app = signedIn()
        app.graph.exercises.saveSet(summary(), t0).getOrThrow()
        val id = app.graph.exercises.history().recent.single().id
        app.server.json("GET /api/v2/me/exercise-sessions") {
            """{"sessions":[{"client_session_id":"$id","status":"rejected","xp_awarded":0},{"client_session_id":"other","status":"verified","xp_awarded":9}]}"""
        }
        assertTrue(app.graph.exercises.sync())
        val s = app.graph.exercises.history().recent.single()
        assertEquals("rejected", s.serverStatus)
        assertEquals(0, s.xpAwarded)
        assertTrue(app.graph.exercises.history().bests.isEmpty())
    }

    @Test
    fun `another account's sets are forgotten on sign-in`() = test {
        val db = Files.createTempFile("osiris", ".db").toFile().apply { deleteOnExit() }
        val url = "jdbc:sqlite:${db.absolutePath}"
        val first = signedIn(TestApp(dbUrl = url))
        first.graph.exercises.saveSet(summary(), t0).getOrThrow()
        val second = signedIn(TestApp(settings = first.settings, dbUrl = url), id = 8)
        assertTrue(second.graph.exercises.history().recent.isEmpty())
        val back = signedIn(TestApp(settings = second.settings, dbUrl = url), id = 7)
        assertTrue(back.graph.exercises.history().recent.isEmpty())
    }

    @Test
    fun `the database is not opened when the same account signs in again`() = test {
        var opens = 0
        val settings = com.russhwolf.settings.MapSettings()
        settings.putInt("osiris.exercise_owner.v1", 7)
        signedIn(TestApp(settings = settings, openDatabase = { opens++; JvmPlatform.openJvmDatabase() }))
        assertEquals(0, opens)
    }

    @Test
    fun `without a database the catalog still loads and saving reports the failure`() = test {
        val app = signedIn(TestApp(openDatabase = { error("disk full") }))
        val catalog = app.graph.exercises.catalog().getOrThrow()
        assertTrue(catalog.exercises.isNotEmpty())
        assertTrue(app.graph.exercises.history().recent.isEmpty())
        assertIs<AppError.Storage>(app.graph.exercises.saveSet(summary(), t0).errorOrNull())
    }

    @Test
    fun `catalog comes from the bundle first, then the cached server copy`() = test {
        val app = signedIn()
        val bundled = app.graph.exercises.catalog().getOrThrow()
        val doc = app.graph.api.json.parseToJsonElement(com.osiris.shared.data.exercise.BundledCatalog.JSON).jsonObject
        val newer = kotlinx.serialization.json.JsonObject(doc + ("rules_version" to kotlinx.serialization.json.JsonPrimitive("2099.1")))
        app.server.json("GET /api/v2/exercises") { newer.toString() }
        app.graph.exercises.catalog()
        // The refresh runs in the background; wait for it to land in the cache.
        var version = bundled.rulesVersion
        for (attempt in 1..100) {
            version = app.graph.exercises.catalog().getOrThrow().rulesVersion
            if (version == "2099.1") break
            delay(20)
        }
        assertEquals("2099.1", version)
        assertTrue(bundled.rulesVersion != "2099.1")
    }

    @Test
    fun `consent falls back to the last known answer offline, per account`() = test {
        val app = signedIn()
        app.server.json("GET /api/v2/me/exercise-consent") { """{"granted":true}""" }
        assertTrue(app.graph.exercises.consent())
        app.server.offline = true
        assertTrue(app.graph.exercises.consent())
        app.server.offline = false
        app.server.json("PUT /api/v2/me/exercise-consent") { """{"granted":false}""" }
        app.graph.exercises.saveSet(summary(), t0).getOrThrow()
        assertFalse(app.graph.exercises.setConsent(false, deleteData = true).getOrThrow())
        assertTrue(app.graph.exercises.history().recent.isEmpty())
    }

    @Test
    fun `QA recordings are written to the recordings folder`() = test {
        val dir = Files.createTempDirectory("rec").toFile().apply { deleteOnExit() }
        val app = signedIn(TestApp(recordingsDir = dir.absolutePath))
        val rec = PoseRecording("squat", "2026.05.1", t0, "device", emptyList(), labelReps = 3)
        val path = app.graph.exercises.saveRecording(rec).getOrThrow()
        assertEquals(rec, PoseRecording.parse(java.io.File(path).readText()))
    }

    @Test
    fun `saving 20 sets and reading history stays fast`() = test {
        val app = signedIn()
        app.server.offline = true
        val started = System.nanoTime()
        repeat(20) { app.graph.exercises.saveSet(summary(valid = 12), t0 + it.minutes).getOrThrow() }
        val history = app.graph.exercises.history()
        val ms = (System.nanoTime() - started) / 1e6
        assertEquals(20, history.recent.size)
        assertTrue(ms < 2_000, "took $ms ms")
    }
}
