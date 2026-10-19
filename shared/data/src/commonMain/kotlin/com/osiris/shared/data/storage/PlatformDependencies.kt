package com.osiris.shared.data.storage

import app.cash.sqldelight.db.SqlDriver
import com.osiris.shared.core.logging.Logger
import com.russhwolf.settings.Settings
import io.ktor.client.engine.HttpClientEngine

/**
 * Everything the shared code needs from the host platform, built once by each app
 * (`AndroidPlatform.create(context)`, `IosPlatform.create()`) and by tests with fakes.
 *
 * @property settings non-secret preferences (install id, cached consent, queued run)
 * @property openDatabase opens the exercise database; called lazily, off the main thread
 * @property recordingsDir where QA pose recordings are written, or null where recording is off
 */
class PlatformDependencies(
    val settings: Settings,
    val secureStore: SecureStore,
    val httpEngine: HttpClientEngine,
    val openDatabase: () -> SqlDriver,
    val logger: Logger,
    val recordingsDir: String?,
)
