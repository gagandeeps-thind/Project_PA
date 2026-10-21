package com.osiris.shared.domain.exercise

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/** Ported from the retired Flutter app's rep_engine_test.dart: same scenarios, same expectations. */
class RepEngineTest {
    private val catalog = loadCatalog()

    private fun run(key: String, frames: List<PoseFrame>) = judge(catalog, key, frames)

    /** Push-up seen from the side: body horizontal, elbow angle swings between [top] and [bottom]. */
    private fun pushups(
        tempo: List<Int>,
        top: Double = 170.0,
        bottom: Double = 80.0,
        hip: Double = 178.0,
        seed: Int = 1,
        torsoDeg: Double = 190.0,
        wristLikelihood: Double = 0.95,
    ): List<PoseFrame> {
        val noise = Noise(seed)
        return cycles(tempo) { p, _ ->
            val body = sideBody(torsoDeg = torsoDeg, elbow = swing(p, top, bottom), shoulder = 80.0, hip = hip, noise = noise).toMutableMap()
            if (wristLikelihood < 0.95) {
                for (s in listOf("left", "right")) {
                    val w = body.getValue("${s}_wrist")
                    body["${s}_wrist"] = Landmark(w.x, w.y, wristLikelihood)
                }
            }
            body
        }
    }

    @Test
    fun bundledCatalogParsesAndListsEveryExercise() {
        assertEquals("exercise-rules-v2", catalog.rulesVersion)
        assertEquals(listOf("pushup", "squat", "lunge", "situp", "jumping_jack", "high_knees", "plank"), catalog.exercises.map { it.key })
        assertTrue("no_valid_reps" in catalog.sessionRules.hardReasons)
    }

    @Test
    fun pushupGenuineRepsWithHumanTempoAreVerified() {
        val s = run("pushup", pushups(humanTempo(12, 1600)))
        assertEquals(12, s.repsValid)
        assertEquals(12, s.repsAttempted)
        assertEquals(Verdict.VERIFIED, s.verdict, "${s.reasons}")
        assertTrue(s.formScore > 0.9)
        assertTrue(s.validRepDurationsS.all { it in 0.6..8.0 })
    }

    @Test
    fun pushupHalfRepsNeverCount() {
        val s = run("pushup", pushups(humanTempo(8, 1400), bottom = 118.0))
        assertEquals(0, s.repsValid)
        assertTrue(s.reasons.containsAll(listOf("partial_range", "no_valid_reps")))
        assertEquals(Verdict.REJECTED, s.verdict)
    }

    @Test
    fun pushupTinyWobblesAreNotAttempts() {
        val s = run("pushup", pushups(humanTempo(8, 1400), bottom = 140.0))
        assertEquals(0, s.repsAttempted)
        assertEquals(Verdict.REJECTED, s.verdict)
    }

    @Test
    fun pushupBouncingIsTooFast() {
        val s = run("pushup", pushups(List(10) { 450 }, seed = 2))
        assertEquals(0, s.repsValid)
        assertTrue("too_fast" in s.reasons)
        assertEquals(Verdict.REJECTED, s.verdict)
    }

    @Test
    fun pushupSaggingHipsBreakForm() {
        val s = run("pushup", pushups(humanTempo(8, 1600), hip = 125.0, torsoDeg = 205.0))
        assertEquals(0, s.repsValid)
        assertTrue("form_break" in s.reasons, "${s.reasons}")
    }

    @Test
    fun armCurlsWhileStandingAreNotPushups() {
        val s = run("pushup", pushups(humanTempo(8, 1600), torsoDeg = -90.0))
        assertEquals(0, s.repsValid)
        assertTrue("wrong_position" in s.reasons)
        assertEquals(Verdict.REJECTED, s.verdict)
    }

    @Test
    fun hiddenWristsProduceNoReps() {
        val s = run("pushup", pushups(humanTempo(8, 1600), wristLikelihood = 0.2))
        assertEquals(0, s.repsAttempted)
        assertEquals(Verdict.REJECTED, s.verdict)
    }

    @Test
    fun aTeleportingTrackerIsAGlitchNotARep() {
        val noise = Noise(3)
        // Alternates between two unrelated detections every few frames.
        val frames = (0 until 400).map { i ->
            val elbow = if ((i / 3) % 2 == 0) 170.0 else 70.0
            PoseFrame(i * 33L, sideBody(torsoDeg = 190.0, elbow = elbow, shoulder = 80.0, noise = noise))
        }
        val s = run("pushup", frames)
        assertEquals(0, s.repsValid)
        assertEquals(Verdict.REJECTED, s.verdict)
    }

    @Test
    fun machineIdenticalTimingIsFlaggedAsAReplay() {
        val s = run("pushup", pushups(List(10) { 1500 }))
        assertEquals(10, s.repsValid)
        assertTrue("replay_suspected" in s.reasons)
        assertEquals(Verdict.REVIEW, s.verdict)
    }

    @Test
    fun mostlyBadSetsGoToReview() {
        val good = pushups(humanTempo(3, 1600))
        val bad = pushups(humanTempo(6, 1400), bottom = 118.0, seed = 4)
        val shifted = bad.map { PoseFrame(it.tMs + good.last().tMs + 33, it.landmarks) }
        val s = run("pushup", good + shifted)
        assertEquals(3, s.repsValid)
        assertTrue("low_valid_ratio" in s.reasons)
        assertEquals(Verdict.REVIEW, s.verdict)
    }

    @Test
    fun liveUpdatesCountRepsAndCoachThePlayer() {
        val engine = RepEngine(catalog.byKey("pushup")!!, catalog)
        val updates = pushups(humanTempo(3, 1600)).map(engine::addFrame)
        assertEquals(3, updates.last().validReps)
        assertEquals(3, updates.count { it.newRep != null })
        assertTrue(updates.any { it.hint == "Go lower" })
        assertTrue(updates.any { it.hint == "Nice rep" })
    }

    @Test
    fun squatsCountAndFoldingTheTorsoBreaksForm() {
        val noise = Noise(5)
        fun squats(hipBottom: Double, lean: Double) = cycles(humanTempo(10, 2200)) { p, _ ->
            sideBody(torsoDeg = -90 + swing(p, 0.0, lean), knee = swing(p, 175.0, 80.0), hip = swing(p, 175.0, hipBottom), noise = noise)
        }
        val good = run("squat", squats(85.0, 40.0))
        assertEquals(10, good.repsValid)
        assertEquals(Verdict.VERIFIED, good.verdict, "${good.reasons}")
        val folded = run("squat", squats(35.0, 90.0))
        assertEquals(0, folded.repsValid)
        // Rejected either by the hip angle (form) or because the torso is no longer upright (position).
        assertTrue(folded.reasons.any { it == "form_break" || it == "wrong_position" })
    }

    @Test
    fun alternatingLungesCountEachLeg() {
        val noise = Noise(6)
        val frames = cycles(humanTempo(10, 2400)) { p, leg ->
            val knee = swing(p, 172.0, 90.0)
            val hip = swing(p, 175.0, 100.0)
            if (leg % 2 == 0) sideBody(knee = knee, hip = hip, farKnee = 172.0, farHip = 175.0, noise = noise)
            else sideBody(knee = 172.0, hip = 175.0, farKnee = knee, farHip = hip, noise = noise)
        }
        val s = run("lunge", frames)
        assertEquals(10, s.repsValid)
        assertEquals(Verdict.VERIFIED, s.verdict, "${s.reasons}")
    }

    @Test
    fun situpsCountWhenLyingDown() {
        val noise = Noise(7)
        val frames = cycles(humanTempo(10, 2400)) { p, _ -> sideBody(thighDeg = -40.0, knee = 70.0, hip = swing(p, 140.0, 55.0), noise = noise) }
        val s = run("situp", frames)
        assertEquals(10, s.repsValid, "${s.reasons}")
        assertEquals(Verdict.VERIFIED, s.verdict)
    }

    @Test
    fun jumpingJacksNeedArmsUpAndLegsApart() {
        val noise = Noise(8)
        val good = run("jumping_jack", cycles(humanTempo(15, 900), pauseMs = 100) { p, _ ->
            frontBody(arm = swing(p, 20.0, 165.0), spread = swing(p, 1.0, 2.2), noise = noise)
        })
        assertEquals(15, good.repsValid)
        assertEquals(Verdict.VERIFIED, good.verdict, "${good.reasons}")
        val armsOnly = run("jumping_jack", cycles(humanTempo(15, 900), pauseMs = 100) { p, _ ->
            frontBody(arm = swing(p, 20.0, 165.0), spread = 1.0, noise = noise)
        })
        assertEquals(0, armsOnly.repsValid)
        assertTrue("form_break" in armsOnly.reasons)
    }

    private fun highKnees(n: Int, fps: Int, seed: Int) = Noise(seed).let { noise ->
        cycles(humanTempo(n, 600), fps = fps, pauseMs = 60) { p, i ->
            val lift = swing(p, 178.0, 95.0)
            val knee = swing(p, 178.0, 90.0)
            if (i % 2 == 0) sideBody(hip = lift, knee = knee, farHip = 178.0, farKnee = 178.0, noise = noise)
            else sideBody(hip = 178.0, knee = 178.0, farHip = lift, farKnee = knee, noise = noise)
        }
    }

    @Test
    fun highKneesCountEachLift() {
        val s = run("high_knees", highKnees(20, 30, 9))
        assertEquals(20, s.repsValid, "${s.reasons}")
        assertEquals(Verdict.VERIFIED, s.verdict)
    }

    private fun plank(sitFirst: Boolean, holdMs: Long, noise: Noise?): List<PoseFrame> {
        val frames = mutableListOf<PoseFrame>()
        var t = 0L
        if (sitFirst) {
            while (t < 2000) {
                frames += PoseFrame(t, sideBody(torsoDeg = -90.0, hip = 90.0, knee = 178.0, noise = noise)); t += 33
            }
        }
        val end = t + holdMs
        while (t < end) {
            frames += PoseFrame(t, sideBody(torsoDeg = 190.0, knee = 178.0, hip = 176.0, shoulder = 80.0, elbow = 90.0, noise = noise)); t += 33
        }
        return frames
    }

    @Test
    fun plankEnteredFromSittingIsTimedAndVerified() {
        val s = run("plank", plank(true, 30000, Noise(10)))
        assertEquals(30.0, s.holdS, 0.5)
        assertEquals(Verdict.VERIFIED, s.verdict, "${s.reasons}")
    }

    @Test
    fun plankStartingAlreadyInPositionIsNotTrusted() {
        val s = run("plank", plank(false, 30000, Noise(11)))
        assertTrue("no_entry_transition" in s.reasons)
        assertEquals(Verdict.REJECTED, s.verdict)
    }

    @Test
    fun aPerfectlyFrozenPlankIsStatic() {
        val s = run("plank", plank(true, 30000, null))
        assertTrue("static_pose" in s.reasons)
        assertEquals(Verdict.REJECTED, s.verdict)
    }

    @Test
    fun standingStraightIsNotAPlank() {
        val noise = Noise(12)
        val frames = (0L until 2000L step 33).map { PoseFrame(it, sideBody(knee = 90.0, hip = 100.0, noise = noise)) } +
            (2000L until 32000L step 33).map { PoseFrame(it, sideBody(noise = noise)) }
        val s = run("plank", frames)
        assertEquals(0.0, s.holdS)
        assertTrue("hold_too_short" in s.reasons)
    }

    @Test
    fun anUnsteadyTrackerIsRefusedNeverCounted() {
        // ~16 px of jitter on a 60 px forearm: a half rep and a full rep look alike.
        val noise = Noise(31, px = 16.0)
        val frames = cycles(humanTempo(10, 1600)) { p, _ -> sideBody(torsoDeg = 190.0, elbow = swing(p, 170.0, 118.0), shoulder = 80.0, noise = noise) }
        val s = run("pushup", frames)
        assertEquals(0, s.repsValid)
        assertTrue("unsteady_tracking" in s.reasons)
        assertEquals(Verdict.REJECTED, s.verdict)
    }

    @Test
    fun steadyTrackingIsNeverCalledUnsteady() {
        val s = run("pushup", pushups(humanTempo(12, 1600)))
        assertTrue("unsteady_tracking" !in s.reasons)
        assertEquals(12, s.repsValid)
    }

    @Test
    fun highKneesAt10FpsStillCountEveryLift() {
        assertEquals(16, run("high_knees", highKnees(16, 10, 32)).repsValid)
    }

    @Test
    fun repDurationsAreInterpolatedNotSnappedToTheFrameGrid() {
        // Identical 1.5 s cycles at 7 fps (143 ms frames): snapped durations would jump by a frame.
        val frames = cycles(List(6) { 1500 }, fps = 7, pauseMs = 400) { p, _ -> sideBody(torsoDeg = 190.0, elbow = swing(p, 170.0, 80.0), shoulder = 80.0) }
        val durations = run("pushup", frames).validRepDurationsS
        assertEquals(6, durations.size)
        assertTrue(durations.max() - durations.min() < 0.06, "$durations")
    }

    @Test
    fun durationCvMatchesTheServerFormula() {
        assertEquals(0.0, durationCv(listOf(1.0, 1.0, 1.0)))
        assertEquals(1.0, durationCv(listOf(1.0)))
        assertEquals(0.5, durationCv(listOf(1.0, 3.0)), 1e-9)
    }

    @Test
    fun perFrameCostStaysFarBelowTheCameraFrameBudget() {
        val frames = pushups(humanTempo(300, 1600))
        // Warm the JIT once so the measurement reflects steady-state cost, as on a running phone.
        judge(catalog, "pushup", frames.take(2000))
        val engine = RepEngine(catalog.byKey("pushup")!!, catalog)
        val start = System.nanoTime()
        frames.forEach(engine::addFrame)
        val usPerFrame = (System.nanoTime() - start) / 1000.0 / frames.size
        // 33 ms is the budget at 30 fps; the engine must use a tiny fraction of it.
        assertTrue(usPerFrame < 200, "$usPerFrame µs/frame over ${frames.size} frames")
        assertEquals(300, engine.finish().repsValid)
        println("PERF rep engine: ${"%.2f".format(usPerFrame)} µs/frame over ${frames.size} frames")
    }
}
