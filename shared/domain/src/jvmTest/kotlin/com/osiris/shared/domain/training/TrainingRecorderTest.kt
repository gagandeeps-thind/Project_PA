package com.osiris.shared.domain.training

import com.osiris.shared.domain.run.LocationFix
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlin.time.Instant

class TrainingRecorderTest {
    private val t0 = Instant.fromEpochSeconds(1_800_000_000)
    private fun at(s: Double) = Instant.fromEpochMilliseconds(t0.toEpochMilliseconds() + (s * 1000).toLong())

    @Test
    fun `recorder keeps one point per second`() {
        val r = TrainingRecorder(t0)
        r.add(Channel.HR, 100.0, at(0.0))
        r.add(Channel.HR, 101.0, at(0.4))
        r.add(Channel.HR, 102.0, at(1.0))
        assertEquals(listOf(listOf(0.0, 100.0), listOf(1.0, 102.0)), r.series().hr)
        assertEquals(102.0, r.latest(Channel.HR))
    }

    @Test
    fun `recorder pause excludes time`() {
        val r = TrainingRecorder(t0)
        r.pause(at(10.0))
        r.add(Channel.HR, 120.0, at(15.0))
        r.resume(at(20.0))
        assertEquals(20.0, r.elapsedS(at(30.0)), 1e-9)
        assertTrue(r.series().hr.isEmpty())
        r.add(Channel.HR, 130.0, at(25.0))
        assertEquals(listOf(listOf(15.0, 130.0)), r.series().hr)
    }

    @Test
    fun `recorder with no samples still has duration`() {
        val r = TrainingRecorder(t0)
        assertEquals(42.0, r.elapsedS(at(42.0)), 1e-9)
        assertNull(r.latest(Channel.POWER))
        assertEquals(0.0, r.distanceM)
        assertTrue(r.series().isEmpty)
    }

    @Test
    fun `downsample caps at 720`() {
        val r = TrainingRecorder(t0)
        repeat(2000) { r.add(Channel.POWER, it.toDouble(), at(it.toDouble())) }
        val power = r.series().power
        assertEquals(720, power.size)
        assertTrue(power.first()[0] < power.last()[0])
        assertTrue(power.zipWithNext().all { (a, b) -> a[0] < b[0] })
    }

    @Test
    fun `gps distance accumulates and gps speed yields to sensor speed`() {
        val r = TrainingRecorder(t0)
        r.addFix(LocationFix(45.0, -66.0, accuracyM = 5.0, speedMps = 2.0, altitudeM = 10.0), at(0.0))
        r.addFix(LocationFix(45.001, -66.0, accuracyM = 5.0, speedMps = 2.0, altitudeM = 12.0), at(60.0))
        assertEquals(111.2, r.distanceM, 0.5)
        assertEquals(listOf(listOf(0.0, 10.0), listOf(60.0, 12.0)), r.series().elevation)
        assertEquals(2.0, r.latest(Channel.SPEED))
        // A sensor reports speed: GPS speed is ignored while the sensor is fresh.
        r.add(Channel.SPEED, 3.0, at(61.0))
        r.addFix(LocationFix(45.002, -66.0, accuracyM = 5.0, speedMps = 9.0), at(62.0))
        assertEquals(3.0, r.latest(Channel.SPEED))
    }

    @Test
    fun `inaccurate fixes and fixes while paused add no distance`() {
        val r = TrainingRecorder(t0)
        r.addFix(LocationFix(45.0, -66.0, accuracyM = 5.0), at(0.0))
        r.addFix(LocationFix(45.01, -66.0, accuracyM = 200.0), at(10.0))
        assertEquals(0.0, r.distanceM)
        r.pause(at(20.0))
        r.addFix(LocationFix(45.01, -66.0, accuracyM = 5.0), at(30.0))
        r.resume(at(40.0))
        r.addFix(LocationFix(45.01, -66.0, accuracyM = 5.0), at(50.0))
        assertEquals(0.0, r.distanceM)
    }

    @Test
    fun `a jump no athlete could make adds no distance and re-anchors`() {
        val r = TrainingRecorder(t0)
        // A stale cached fix far away, then the real position: ~3,500 km in 4 s.
        r.addFix(LocationFix(19.0, -70.0, accuracyM = 5.0), at(0.0))
        r.addFix(LocationFix(45.96, -66.64, accuracyM = 5.0), at(4.0))
        assertEquals(0.0, r.distanceM)
        // Movement from the new anchor still counts.
        r.addFix(LocationFix(45.961, -66.64, accuracyM = 5.0), at(40.0))
        assertEquals(111.2, r.distanceM, 0.5)
    }

    @Test
    fun `indoor distance comes from sensor speed when there is no gps`() {
        val r = TrainingRecorder(t0)
        r.add(Channel.SPEED, 5.0, at(0.0))
        r.add(Channel.SPEED, 5.0, at(10.0))
        assertEquals(50.0, r.distanceM, 1e-9)
    }
}
