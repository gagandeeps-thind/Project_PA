package com.osiris.shared.data

import com.osiris.shared.domain.model.NewTrainingSession
import com.osiris.shared.domain.model.TrainingSeries
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

class TrainingRepositoryTest {
    private val session = """{"id":5,"activity_key":"run","mode":"challenge","source":"sensor",
        "started_at":"2026-11-02T08:00:00","duration_s":600.0,"distance_m":2000.0,"elevation_gain_m":3.0,"reps":0,
        "posted":false,"is_pr":true}"""

    @Test
    fun `quote is fetched once per launch and skips the one shown last launch`() = test {
        val app = TestApp()
        app.server.json("GET /api/v2/motivation/quote") { """{"id":4,"text":"Go","author":"Osiris"}""" }
        val first = app.graph.training
        assertEquals(4, first.quote().getOrThrow().id)
        first.quote().getOrThrow()
        assertEquals(1, app.server.count("GET /api/v2/motivation/quote"))
        assertEquals("", app.server.calls.single().query)

        // A new launch: same settings, new repository.
        val relaunch = TestApp(server = app.server, settings = app.settings)
        relaunch.graph.training.quote().getOrThrow()
        assertEquals("exclude=4", app.server.calls.last().query)
    }

    @Test
    fun `upload sends the session body and reads the saved session`() = test {
        val app = TestApp()
        app.server.json("POST /api/v2/training/sessions", status = 201) { session }
        val saved = app.graph.training.upload(
            NewTrainingSession(
                clientSessionId = "abc", activityKey = "run", mode = "challenge", source = "sensor",
                startedAt = "2026-11-02T08:00:00Z", durationS = 600.0, distanceM = 2000.0,
                series = TrainingSeries(hr = listOf(listOf(0.0, 120.0))),
            ),
        ).getOrThrow()
        val body = app.server.calls.single().body!!.jsonObject
        assertEquals("abc", body["client_session_id"]!!.jsonPrimitive.content)
        assertEquals("challenge", body["mode"]!!.jsonPrimitive.content)
        assertEquals(true, saved.isPr)
        assertEquals(5, saved.id)
    }

    @Test
    fun `activities are cached`() = test {
        val app = TestApp()
        app.server.json("GET /api/v2/training/activities") {
            """[{"key":"run","name":"Run","kind":"gps","metric":"distance_m","max_speed_mps":12.5,"gps":true}]"""
        }
        app.graph.training.activities().getOrThrow()
        assertEquals("Run", app.graph.training.activities().getOrThrow().single().name)
        assertEquals(1, app.server.count("GET /api/v2/training/activities"))
    }
}
