package com.osiris.shared.data.repository

import com.osiris.shared.domain.repository.DeviceSetupRepository
import com.russhwolf.settings.Settings
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** Install-scoped flags in plain settings: neither is a secret, and both survive sign-out. */
class DeviceSetupRepositoryImpl(private val settings: Settings) : DeviceSetupRepository {
    private val _primerCompleted = MutableStateFlow(settings.getBoolean(KEY_PRIMER, false))
    private val _telemetryConsent = MutableStateFlow(settings.getBoolean(KEY_TELEMETRY, false))

    override val primerCompleted: StateFlow<Boolean> = _primerCompleted.asStateFlow()
    override val telemetryConsent: StateFlow<Boolean> = _telemetryConsent.asStateFlow()

    override suspend fun completePrimer() {
        settings.putBoolean(KEY_PRIMER, true)
        _primerCompleted.value = true
    }

    override suspend fun setTelemetryConsent(granted: Boolean) {
        settings.putBoolean(KEY_TELEMETRY, granted)
        _telemetryConsent.value = granted
    }

    private companion object {
        const val KEY_PRIMER = "device_setup.primer_completed"
        const val KEY_TELEMETRY = "device_setup.telemetry_consent"
    }
}
