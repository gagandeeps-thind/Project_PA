package com.osiris.shared.core

import com.osiris.shared.core.config.AppConfig
import com.osiris.shared.core.config.FeatureFlags
import com.osiris.shared.core.error.AppError
import com.osiris.shared.core.error.Outcome
import com.osiris.shared.core.error.outcomeOf
import com.osiris.shared.core.platform.Platform
import com.osiris.shared.core.util.newHexId
import kotlin.coroutines.cancellation.CancellationException
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNotEquals
import kotlin.test.assertTrue

class CoreTest {
    @Test
    fun buildConfigPicksThePlatformBaseUrl() {
        val android = AppConfig.fromBuild(Platform.ANDROID)
        val ios = AppConfig.fromBuild(Platform.IOS)
        assertTrue(android.apiBaseUrl.startsWith("http"))
        assertFalse(android.apiBaseUrl.endsWith("/"))
        assertEquals(android.environment, ios.environment)
    }

    @Test
    fun configRejectsANonHttpUrl() {
        assertFailsWith<IllegalArgumentException> {
            AppConfig("dev", "ftp://x", 1, 1, false, FeatureFlags())
        }
    }

    @Test
    fun transientErrorsAreRetryable() {
        assertTrue(AppError.Offline().isTransient)
        assertTrue(AppError.Timeout().isTransient)
        assertTrue(AppError.Http(503, null, "x").isTransient)
        assertTrue(AppError.Http(429, null, "x").isTransient)
        assertFalse(AppError.Http(422, null, "x").isTransient)
        assertFalse(AppError.Unauthorized().isTransient)
    }

    @Test
    fun outcomeCapturesFailuresButNotCancellation() {
        val failed = outcomeOf { error("boom") }
        assertIs<Outcome.Failure>(failed)
        assertIs<AppError.Unexpected>(failed.error)
        val passthrough = outcomeOf { throw AppError.Validation("bad") }
        assertEquals("bad", passthrough.errorOrNull()?.userMessage)
        assertFailsWith<CancellationException> { outcomeOf { throw CancellationException("stop") } }
    }

    @Test
    fun hexIdsAreRandomAndWellFormed() {
        val a = newHexId()
        assertEquals(32, a.length)
        assertTrue(a.all { it in '0'..'9' || it in 'a'..'f' })
        assertNotEquals(a, newHexId())
    }
}
