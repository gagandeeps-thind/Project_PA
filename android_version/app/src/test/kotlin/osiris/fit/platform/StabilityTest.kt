package osiris.fit.platform

import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import osiris.fit.platform.crash.CrashLog
import osiris.fit.platform.image.sampleSize

class StabilityTest {
    @Test
    fun `a photo is subsampled to at most twice the wanted side, never below it`() {
        assertEquals(1, sampleSize(800, 600, maxSide = 1024))
        assertEquals(1, sampleSize(2047, 1000, maxSide = 1024))
        assertEquals(2, sampleSize(2048, 1536, maxSide = 1024))
        assertEquals(4, sampleSize(8160, 6120, maxSide = 1024)) // a 50 MP camera photo decodes at 2040 x 1530
        assertEquals(16, sampleSize(6120, 8160, maxSide = 384))
    }

    @Test
    fun `a crash record names the build, the thread, the exception and its cause`() {
        val error = IllegalStateException("x".repeat(1000), IllegalArgumentException("root"))
        val record = CrashLog.record("2026-11-16T10:00:00Z", "1.0.1 (2)", "main", error)
        val lines = record.lines()
        assertEquals("2026-11-16T10:00:00Z v1.0.1 (2) thread=main", lines[0])
        assertEquals("java.lang.IllegalStateException: " + "x".repeat(300), lines[1])
        assertTrue(lines[2].startsWith("  at osiris.fit.platform.StabilityTest"))
        assertTrue("Caused by: java.lang.IllegalArgumentException: root" in lines)
        assertTrue(lines.count { it.startsWith("  at ") } <= 24)
    }

    @Test
    fun `the crash file keeps the newest records and stays small`() {
        val file = File.createTempFile("crashes", ".log")
        try {
            repeat(200) { i -> CrashLog.append(file, "crash $i " + "y".repeat(1000)) }
            assertTrue(file.length() < 100_000)
            val text = file.readText()
            assertTrue("crash 199 " in text)
            assertFalse("crash 0 " in text)
        } finally {
            file.delete()
        }
    }
}
