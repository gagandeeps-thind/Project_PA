package com.osiris.shared.domain.repository

import kotlinx.coroutines.flow.StateFlow

/** The device permissions the app explains before sign-in. Each one is optional. */
enum class DevicePermission {
    /** GPS for verified runs and nearby challenges. */
    LOCATION,

    /** Step counter and motion sensors (Android activity recognition, iOS Motion & Fitness). */
    ACTIVITY,

    /** Health Connect / HealthKit steps, distance and energy, used to cross-check runs. */
    HEALTH,

    /** Camera for counted exercise sets; frames never leave the phone. */
    CAMERA,

    /** Challenge start and result notifications. */
    NOTIFICATIONS,
}

enum class PermissionStatus { NOT_ASKED, GRANTED, DENIED }

/**
 * Per-install setup that happens before an account exists: whether the permission primer was
 * finished, and the player's crash/diagnostics telemetry choice (GDPR opt-in, off by default).
 * Permission grants themselves are read from the OS each time, never stored.
 */
interface DeviceSetupRepository {
    val primerCompleted: StateFlow<Boolean>
    val telemetryConsent: StateFlow<Boolean>
    suspend fun completePrimer()
    suspend fun setTelemetryConsent(granted: Boolean)
}
