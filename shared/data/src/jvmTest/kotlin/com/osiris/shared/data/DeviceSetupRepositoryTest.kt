package com.osiris.shared.data

import com.osiris.shared.data.repository.DeviceSetupRepositoryImpl
import com.russhwolf.settings.MapSettings
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlinx.coroutines.test.runTest

class DeviceSetupRepositoryTest {
    @Test
    fun `primer completion and telemetry consent survive a restart and telemetry defaults to off`() = runTest {
        val settings = MapSettings()
        val first = DeviceSetupRepositoryImpl(settings)
        assertFalse(first.primerCompleted.value)
        assertFalse(first.telemetryConsent.value)
        first.completePrimer()
        first.setTelemetryConsent(true)

        val restarted = DeviceSetupRepositoryImpl(settings)
        assertTrue(restarted.primerCompleted.value)
        assertTrue(restarted.telemetryConsent.value)
    }
}
