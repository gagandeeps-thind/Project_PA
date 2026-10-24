package com.osiris.shared.domain.run

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.time.Duration.Companion.milliseconds
import kotlin.time.Duration.Companion.seconds
import kotlin.time.Instant

class ActiveRunTest {
    private val t0 = Instant.parse("2026-10-19T08:00:00Z")
    private val run = ActiveRun(runId = 1, startedAt = t0)

    @Test
    fun pointsUseTheTimeTheFixWasMeasuredNotWhenItArrived() {
        // Fixes measured 1 s apart but delivered 100 ms apart keep their 1 s spacing.
        val next = run
            .withFix(LocationFix(52.0, 4.0, at = t0 + 1.seconds), now = t0 + 1900.milliseconds)
            .withFix(LocationFix(52.0001, 4.0, at = t0 + 2.seconds), now = t0 + 2000.milliseconds)
        assertEquals(listOf(1000L, 2000L), next.pending.map { it.tMs })
        assertEquals(2000L, next.lastTMs)
    }

    @Test
    fun withoutAMeasuredTimeTheArrivalTimeIsUsed() {
        val next = run.withFix(LocationFix(52.0, 4.0), now = t0 + 3.seconds)
        assertEquals(3000L, next.pending.single().tMs)
    }

    @Test
    fun aCachedFixFromBeforeTheStartIsDropped() {
        val next = run.withFix(LocationFix(52.0, 4.0, at = t0 - 30.seconds), now = t0 + 1.seconds)
        assertEquals(run, next)
    }

    @Test
    fun aFixThatIsNotAfterTheLastPointIsDroppedSoTimestampsKeepIncreasing() {
        val first = run.withFix(LocationFix(52.0, 4.0, at = t0 + 2.seconds), now = t0 + 2.seconds)
        val late = first.withFix(LocationFix(52.0001, 4.0, at = t0 + 2.seconds), now = t0 + 3.seconds)
        assertEquals(first, late)
        assertEquals(0, first.pending.single().sequence)
        assertEquals(0.0, late.distanceM)
    }

    /** Fixes 1 s apart heading north at [mps], with the phone's Doppler [speeds] (null: none reported). */
    private fun walk(start: ActiveRun, from: Int, to: Int, mps: (Int) -> Double, altitude: (Int) -> Double? = { null }): ActiveRun {
        var r = start
        var lat = 52.0 + from * 0.00001
        for (i in from until to) {
            lat += mps(i) / 111_195.0
            r = r.withFix(LocationFix(lat, 4.0, speedMps = mps(i), altitudeM = altitude(i), at = t0 + i.seconds), now = t0 + i.seconds)
        }
        return r
    }

    @Test
    fun aStopOfTenSecondsAutoPausesAndLeavesMovingTimeAShortOneDoesNot() {
        val stops = walk(run, 0, 101, { i -> if (i in 30 until 50 || i in 70 until 75) 0.0 else 3.0 })
        // Same figures as the server's test: 100 s elapsed, the 20 s stop paused, the 5 s pause not.
        assertEquals(80.seconds, stops.moving(t0 + 100.seconds))
        val standing = walk(run, 0, 45, { i -> if (i >= 30) 0.0 else 3.0 })
        assertEquals(true, standing.paused)
        assertEquals(29.seconds, standing.moving(t0 + 60.seconds)) // segments ending at fixes 1-29; holds while paused
        val off = walk(run.copy(autoPause = false), 0, 45, { i -> if (i >= 30) 0.0 else 3.0 })
        assertEquals(false, off.paused)
        assertEquals(44.seconds, off.moving(t0 + 44.seconds))
    }

    @Test
    fun aPhoneReportingSpeedZeroWhileClearlyMovingIsNotPaused() {
        var r = run
        for (i in 0 until 30) { // 10 m a second, Doppler speed stuck at 0 (seen on the emulator)
            r = r.withFix(LocationFix(52.0 + i * 0.00009, 4.0, accuracyM = 5.0, speedMps = 0.0, at = t0 + i.seconds), now = t0 + i.seconds)
        }
        assertEquals(false, r.paused)
        assertEquals(29.seconds, r.moving(t0 + 29.seconds))
    }

    @Test
    fun elevationGainCountsClimbsAndIgnoresGpsAltitudeNoise() {
        val alts = listOf(10.0, 12.0, 11.0, 12.5, 10.0, 20.0, 19.0, 25.0, null, 24.0, 30.0)
        val climbed = walk(run, 0, alts.size, { 3.0 }, { i -> alts[i] })
        assertEquals(22.0, climbed.elevationGainM) // 10 + 6 + 6, as on the server
    }
}
