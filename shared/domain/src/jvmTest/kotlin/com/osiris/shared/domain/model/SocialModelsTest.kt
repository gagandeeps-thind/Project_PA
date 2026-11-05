package com.osiris.shared.domain.model

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlin.time.Instant
import kotlinx.serialization.json.Json

class SocialModelsTest {
    private val json = Json { ignoreUnknownKeys = true }
    private val start = Instant.parse("2026-11-05T07:00:00Z")

    @Test
    fun `a run shows distance, time and pace, and a camera set shows reps`() {
        val run = PostAttachment(1, "run", "Run", "gps", start, durationS = 1500.0, distanceM = 5000.0, hrAvg = 151.6)
        assertEquals(
            listOf("Distance" to "5.00 km", "Time" to "25:00", "Pace" to "5:00 /km", "Avg HR" to "151 bpm"),
            run.tiles.map { it.label to it.value },
        )
        val pushups = PostAttachment(2, "pushup", "Push-ups", "camera", start, durationS = 60.0, reps = 30)
        assertEquals(listOf("Time" to "1:00", "Reps" to "30"), pushups.tiles.map { it.label to it.value })
    }

    @Test
    fun `a post decodes the server's photo, attachments and chart`() {
        val post = json.decodeFromString(
            FeedPost.serializer(),
            """{"id":3,"user_id":9,"photo_url":"/api/v2/social/media/abc","created_at":"2026-11-05T08:00:00",
               "attachments":[{"session_id":1,"activity_key":"run","started_at":"2026-11-05T07:00:00","distance_m":5000}],
               "chart":{"kind":"weekly_progress","values":[0,30,0]}}""",
        )
        assertTrue(post.hasMedia)
        assertEquals(start, post.attachments.single().startedAt)
        assertEquals(30.0, post.chart!!.max)
        assertEquals(Instant.parse("2026-11-05T08:00:00Z"), post.createdInstant)
        assertNull(FeedPost(id = 1, userId = 1, createdAt = "garbage").createdInstant)
    }

    @Test
    fun `an empty draft is empty and a chart alone is not`() {
        assertTrue(SocialPostDraft(caption = "  ").isEmpty)
        assertFalse(SocialPostDraft(chart = SocialPostDraft.CHART_WEEKLY).isEmpty)
        assertEquals(1.0, PostChart("weekly_progress").max)
    }
}
