package com.osiris.shared.data.repository

import com.osiris.shared.core.util.newHexId
import com.russhwolf.settings.Settings
import kotlin.coroutines.cancellation.CancellationException

/**
 * Random per-install id for anonymous funnel events. Not tied to device hardware; a reinstall
 * gets a new one. [onCreated] runs once, when the id is first made (the `app_installed` event);
 * its failure never reaches the caller.
 */
class InstallId(private val settings: Settings, private val onCreated: suspend (String) -> Unit = {}) {
    suspend fun get(): String {
        settings.getStringOrNull(KEY)?.let { return it }
        val id = "i-" + newHexId(12)
        settings.putString(KEY, id)
        try {
            onCreated(id)
        } catch (e: CancellationException) {
            throw e
        } catch (_: Throwable) {
            // Analytics only.
        }
        return id
    }

    companion object {
        const val KEY = "install_id"
    }
}
