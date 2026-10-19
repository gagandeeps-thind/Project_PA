package com.osiris.shared.domain.run

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.time.Duration.Companion.milliseconds
import kotlin.time.Duration.Companion.seconds
import kotlin.time.Instant

class ActiveRunTest {
    private val start = Instant.parse("2026-10-19T06:00:00Z")
    private val run = ActiveRun(runId = 1, startedAt = start)

    @Test
    fun pointsAreTimedWhenTheFixWasTakenNotWhenItArrived() {
        val r = run
            .withFix(LocationFix(52.0, 4.0), start + 2.seconds)
            // Arrived 100 ms after the previous one, but was taken 900 ms earlier.
            .withFix(LocationFix(52.0001, 4.0, ageMs = 900), start + 2100.milliseconds)
        assertEquals(listOf(2000L, 2001L), r.pending.map { it.tMs })
    }

    @Test
    fun ageShiftsTheTimestampBack() {
        val r = run
            .withFix(LocationFix(52.0, 4.0), start + 1.seconds)
            .withFix(LocationFix(52.0001, 4.0, ageMs = 400), start + 3.seconds)
        assertEquals(listOf(1000L, 2600L), r.pending.map { it.tMs })
    }

    @Test
    fun fixesTakenBeforeTheRunStartedAreIgnored() {
        val r = run.withFix(LocationFix(52.0, 4.0, ageMs = 60_000), start + 1.seconds)
        assertEquals(0, r.nextSequence)
        assertEquals(0.0, r.distanceM)
    }
}
