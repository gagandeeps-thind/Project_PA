package com.osiris.shared.domain.exercise

import java.io.File
import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNotNull
import kotlin.test.assertTrue
import kotlin.time.Instant

/**
 * Replays every QA landmark recording in shared/testdata/recordings/ through the
 * rep engine and compares the result with the tester's label (port of recordings_replay_test.dart).
 */
class RecordingsReplayTest {
    private val catalog = loadCatalog()

    private fun replay(r: PoseRecording) = judge(catalog, r.exerciseKey, r.frames)

    /** Reps may be off by one at either end of a set; holds by two seconds. */
    private fun assertMatchesLabel(r: PoseRecording, s: SessionSummary, name: String) {
        r.labelReps?.let { assertTrue(abs(s.repsValid - it) <= 1, "$name: counted ${s.repsValid}, label $it (${s.reasons})") }
        r.labelHoldS?.let { assertTrue(abs(s.holdS - it) <= 2.0, "$name: held ${s.holdS} s, label $it s") }
    }

    @Test
    fun aRecordingRoundTripsThroughItsJsonFormatAndReplaysIdentically() {
        val noise = Noise(41)
        val recorder = PoseRecorder()
        val frames = cycles(humanTempo(8, 1600)) { p, _ -> sideBody(torsoDeg = 190.0, elbow = swing(p, 170.0, 80.0), shoulder = 80.0, noise = noise) }
        frames.forEach(recorder::add)
        val original = recorder.finish("pushup", catalog.rulesVersion, Instant.parse("2026-10-19T00:00:00Z"), labelReps = 8)
        val restored = PoseRecording.parse(original.toJson())
        assertEquals(frames.size, restored.frames.size)
        assertEquals(8, restored.labelReps)
        // Stored coordinates are rounded to 0.1 px; the count must not depend on that.
        assertEquals(replay(original).repsValid, replay(restored).repsValid)
        assertMatchesLabel(restored, replay(restored), "round-trip")
    }

    @Test
    fun theRecorderStopsAtItsCap() {
        val recorder = PoseRecorder()
        repeat(PoseRecorder.MAX_FRAMES + 10) { recorder.add(PoseFrame(it.toLong(), emptyMap())) }
        assertEquals(PoseRecorder.MAX_FRAMES, recorder.frames.size)
    }

    @Test
    fun anUnknownFormatIsRefusedNotMisread() {
        assertFailsWith<IllegalArgumentException> { PoseRecording.parse("""{"format":"osiris-pose-v0"}""") }
    }

    @Test
    fun everyRecordingMatchesItsLabel() {
        val dir = File(System.getProperty("osiris.recordings"))
        val files = dir.listFiles { f -> f.name.endsWith(".json") }.orEmpty().sortedBy { it.name }
        assertTrue(files.isNotEmpty(), "no recordings in $dir")
        for (file in files) {
            val r = PoseRecording.parse(file.readText())
            assertNotNull(catalog.byKey(r.exerciseKey), "unknown exercise ${r.exerciseKey}")
            assertNotNull(r.labelReps ?: r.labelHoldS, "${file.name}: an unlabeled recording tests nothing")
            assertMatchesLabel(r, replay(r), file.name)
        }
    }
}
