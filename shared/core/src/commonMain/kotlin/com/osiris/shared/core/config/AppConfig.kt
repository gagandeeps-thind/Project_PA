package com.osiris.shared.core.config

import com.osiris.shared.core.platform.Platform
import com.osiris.shared.core.platform.currentPlatform

/**
 * Runtime configuration. Values come from `config/environments/<env>.properties`, compiled in at build
 * time (see `config/environments/README.md`), so no URL, timeout or flag is hard-coded in app code.
 * Tests and previews build their own instance.
 */
data class AppConfig(
    val environment: String,
    val apiBaseUrl: String,
    val connectTimeoutMs: Long,
    val requestTimeoutMs: Long,
    val httpLogging: Boolean,
    val features: FeatureFlags,
) {
    init {
        require(apiBaseUrl.startsWith("http://") || apiBaseUrl.startsWith("https://")) {
            "apiBaseUrl must be an http(s) URL, was '$apiBaseUrl'"
        }
        require(connectTimeoutMs > 0 && requestTimeoutMs > 0) { "timeouts must be positive" }
    }

    val isProduction: Boolean get() = environment == "prod"

    companion object {
        /** The configuration compiled into this build, with the base URL for this platform. */
        fun fromBuild(platform: Platform = currentPlatform): AppConfig = AppConfig(
            environment = GeneratedEnv.ENVIRONMENT,
            apiBaseUrl = when (platform) {
                Platform.ANDROID -> GeneratedEnv.API_BASE_URL_ANDROID
                Platform.IOS -> GeneratedEnv.API_BASE_URL_IOS
                Platform.JVM -> GeneratedEnv.API_BASE_URL_JVM
            }.trimEnd('/'),
            connectTimeoutMs = GeneratedEnv.API_CONNECT_TIMEOUT_MS,
            requestTimeoutMs = GeneratedEnv.API_REQUEST_TIMEOUT_MS,
            httpLogging = GeneratedEnv.HTTP_LOGGING,
            features = FeatureFlags(
                legacyGame = GeneratedEnv.FEATURE_LEGACY,
                poseRecording = GeneratedEnv.FEATURE_POSE_RECORDING,
            ),
        )
    }
}

/**
 * Build-time feature switches.
 *
 * @property legacyGame bounty, vault and domain screens kept behind a flag while the product
 *   moves to the run, course and challenge loop (Backlog Phase 3).
 * @property poseRecording landmark recording for device QA; never on in production.
 */
data class FeatureFlags(
    val legacyGame: Boolean = false,
    val poseRecording: Boolean = false,
)
