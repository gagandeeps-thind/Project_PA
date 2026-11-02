package com.osiris.shared.domain.training

/**
 * Decoders for the Bluetooth SIG fitness profiles the Start tab reads live: Heart Rate,
 * Cycling Power, Running Speed & Cadence and Cycling Speed & Cadence. Fields are little-endian.
 * A packet too short for the fields its flags announce decodes to null.
 */
object BleParsers {
    const val HEART_RATE_SERVICE = "0000180d-0000-1000-8000-00805f9b34fb"
    const val HR_MEASUREMENT = "00002a37-0000-1000-8000-00805f9b34fb"
    const val CYCLING_POWER_SERVICE = "00001818-0000-1000-8000-00805f9b34fb"
    const val CP_MEASUREMENT = "00002a63-0000-1000-8000-00805f9b34fb"
    const val RSC_SERVICE = "00001814-0000-1000-8000-00805f9b34fb"
    const val RSC_MEASUREMENT = "00002a53-0000-1000-8000-00805f9b34fb"
    const val CSC_SERVICE = "00001816-0000-1000-8000-00805f9b34fb"
    const val CSC_MEASUREMENT = "00002a5b-0000-1000-8000-00805f9b34fb"

    /** Client characteristic configuration descriptor, written to turn notifications on. */
    const val NOTIFY_DESCRIPTOR = "00002902-0000-1000-8000-00805f9b34fb"

    /** Each service and the channel its measurement feeds. */
    val services: Map<String, Channel> = mapOf(
        HEART_RATE_SERVICE to Channel.HR,
        CYCLING_POWER_SERVICE to Channel.POWER,
        RSC_SERVICE to Channel.SPEED,
        CSC_SERVICE to Channel.SPEED,
    )

    /** Each service's measurement characteristic. */
    val measurements: Map<String, String> = mapOf(
        HEART_RATE_SERVICE to HR_MEASUREMENT,
        CYCLING_POWER_SERVICE to CP_MEASUREMENT,
        RSC_SERVICE to RSC_MEASUREMENT,
        CSC_SERVICE to CSC_MEASUREMENT,
    )

    private const val BYTE = 0xFF
    private const val SHIFT_8 = 8
    private const val SHIFT_16 = 16
    private const val UINT16 = 0x10000
    private const val SPEED_RESOLUTION = 256.0
    private const val TICKS_PER_SECOND = 1024.0
    private const val HR_16_BIT = 0x01
    private const val CSC_WHEEL = 0x01
    private const val SINT16_MAX = 0x7FFF

    // Packet sizes and field offsets, in bytes.
    private const val HR8_SIZE = 2
    private const val HR16_SIZE = 3
    private const val CP_SIZE = 4
    private const val CP_POWER = 2
    private const val RSC_SIZE = 3
    private const val CSC_SIZE = 7
    private const val CSC_TICKS = 5
    private const val WORD = 2

    private fun ByteArray.u8(i: Int) = this[i].toInt() and BYTE
    private fun ByteArray.u16(i: Int) = u8(i) or (u8(i + 1) shl SHIFT_8)
    private fun ByteArray.u32(i: Int): Long =
        u16(i).toLong() or (u16(i + WORD).toLong() shl SHIFT_16)

    /** Beats per minute, from the 8- or 16-bit field flag bit 0 selects. */
    fun heartRate(bytes: ByteArray): Int? {
        if (bytes.isEmpty()) return null
        val wide = bytes.u8(0) and HR_16_BIT != 0
        return when {
            wide && bytes.size >= HR16_SIZE -> bytes.u16(1)
            !wide && bytes.size >= HR8_SIZE -> bytes.u8(1)
            else -> null
        }
    }

    /** Instantaneous power in watts: sint16 after the 16-bit flags. */
    fun cyclingPower(bytes: ByteArray): Int? {
        if (bytes.size < CP_SIZE) return null
        val raw = bytes.u16(CP_POWER)
        return if (raw > SINT16_MAX) raw - UINT16 else raw
    }

    /** Instantaneous running speed in m/s: uint16 in 1/256 m/s after the flags byte. */
    fun rscSpeedMps(bytes: ByteArray): Double? = if (bytes.size < RSC_SIZE) null else bytes.u16(1) / SPEED_RESOLUTION

    /** Wheel speed from consecutive CSC packets; [wheelM] is the wheel circumference. */
    class CscSpeed(private val wheelM: Double = 2.105) {
        private var lastRevs: Long? = null
        private var lastTicks = 0

        /** Speed since the previous packet, or null for the first packet or one without wheel data. */
        fun next(bytes: ByteArray): Double? {
            if (bytes.size < CSC_SIZE || bytes.u8(0) and CSC_WHEEL == 0) return null
            val revs = bytes.u32(1)
            val ticks = bytes.u16(CSC_TICKS)
            val previous = lastRevs
            val dt = (ticks - lastTicks + UINT16) % UINT16
            lastRevs = revs
            lastTicks = ticks
            return if (previous == null || dt == 0) null
            else (revs - previous).coerceAtLeast(0) * wheelM / (dt / TICKS_PER_SECOND)
        }
    }
}
