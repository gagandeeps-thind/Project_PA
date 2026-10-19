package com.osiris.shared.data.storage

/**
 * Small secrets (the session token) in the platform's protected storage: the Android Keystore
 * and the iOS Keychain. Never use [com.russhwolf.settings.Settings] for credentials.
 */
interface SecureStore {
    suspend fun get(key: String): String?
    suspend fun put(key: String, value: String)
    suspend fun remove(key: String)
}

/** Process-memory store for tests and the JVM tooling target. Not persistent, not for devices. */
class InMemorySecureStore : SecureStore {
    private val values = mutableMapOf<String, String>()
    override suspend fun get(key: String): String? = values[key]
    override suspend fun put(key: String, value: String) {
        values[key] = value
    }
    override suspend fun remove(key: String) {
        values.remove(key)
    }
}
