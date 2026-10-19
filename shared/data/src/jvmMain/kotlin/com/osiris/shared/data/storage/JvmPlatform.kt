package com.osiris.shared.data.storage

import app.cash.sqldelight.driver.jdbc.sqlite.JdbcSqliteDriver
import com.osiris.shared.core.logging.platformLogger
import com.osiris.shared.data.db.OsirisDatabase
import com.osiris.shared.data.network.platformHttpEngine
import com.russhwolf.settings.PreferencesSettings
import java.util.Properties
import java.util.prefs.Preferences

/** JVM host (tests, tooling): preferences-backed settings, in-memory secrets, SQLite at [databaseUrl]. */
object JvmPlatform {
    fun create(databaseUrl: String = JdbcSqliteDriver.IN_MEMORY, recordingsDir: String? = null): PlatformDependencies =
        PlatformDependencies(
            settings = PreferencesSettings(Preferences.userRoot().node("com/osiris/shared")),
            secureStore = InMemorySecureStore(),
            httpEngine = platformHttpEngine(),
            openDatabase = { openJvmDatabase(databaseUrl) },
            logger = platformLogger(),
            recordingsDir = recordingsDir,
        )

    fun openJvmDatabase(url: String = JdbcSqliteDriver.IN_MEMORY) =
        JdbcSqliteDriver(url, Properties().apply { put("foreign_keys", "true") }, OsirisDatabase.Schema)
}
