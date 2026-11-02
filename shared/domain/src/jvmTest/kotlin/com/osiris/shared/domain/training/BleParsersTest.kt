package com.osiris.shared.domain.training

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class BleParsersTest {
    private fun bytes(vararg v: Int) = ByteArray(v.size) { v[it].toByte() }

    @Test
    fun `hr uint8 format`() {
        assertEquals(72, BleParsers.heartRate(bytes(0x00, 0x48)))
    }

    @Test
    fun `hr uint16 format`() {
        assertEquals(120, BleParsers.heartRate(bytes(0x01, 0x78, 0x00)))
        assertEquals(300, BleParsers.heartRate(bytes(0x01, 0x2C, 0x01)))
    }

    @Test
    fun `short packets decode to null`() {
        assertNull(BleParsers.heartRate(bytes(0x01, 0x78)))
        assertNull(BleParsers.cyclingPower(bytes(0, 0, 0xFA)))
        assertNull(BleParsers.rscSpeedMps(bytes(0)))
    }

    @Test
    fun `cycling power`() {
        assertEquals(250, BleParsers.cyclingPower(bytes(0, 0, 0xFA, 0x00)))
    }

    @Test
    fun `rsc speed`() {
        assertEquals(3.0, BleParsers.rscSpeedMps(bytes(0, 0x00, 0x03))!!, 1e-9)
    }

    @Test
    fun `csc speed from two packets`() {
        val csc = BleParsers.CscSpeed()
        // Flags: wheel data present; revolutions uint32, last event time uint16 in 1/1024 s.
        assertNull(csc.next(bytes(0x01, 10, 0, 0, 0, 0x00, 0x04)))
        assertEquals(2.105, csc.next(bytes(0x01, 11, 0, 0, 0, 0x00, 0x08))!!, 1e-9)
    }

    @Test
    fun `csc speed survives the event timer rolling over`() {
        val csc = BleParsers.CscSpeed()
        csc.next(bytes(0x01, 10, 0, 0, 0, 0x00, 0xFC))
        // 0xFC00 -> 0x0000 is 1024 ticks later.
        assertEquals(2.105, csc.next(bytes(0x01, 11, 0, 0, 0, 0x00, 0x00))!!, 1e-9)
    }
}
