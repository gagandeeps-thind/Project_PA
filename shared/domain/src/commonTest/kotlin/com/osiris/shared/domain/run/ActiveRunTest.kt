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
}
