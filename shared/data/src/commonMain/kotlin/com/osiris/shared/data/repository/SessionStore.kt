package com.osiris.shared.data.repository

import com.osiris.shared.core.error.AppError
import com.osiris.shared.data.network.TokenProvider
import com.osiris.shared.data.storage.SecureStore
import com.osiris.shared.domain.model.Session
import kotlin.coroutines.cancellation.CancellationException
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/**
 * The session token in secure storage, cached in memory after the first read so each request
 * does not hit the Keystore or Keychain. It is the [TokenProvider] for the API client.
 */
class SessionStore(private val secure: SecureStore) : TokenProvider {
    private val lock = Mutex()
    private var loaded = false
    private var cached: Session? = null

    override suspend fun token(): String? = current()?.token

    suspend fun current(): Session? = lock.withLock {
        if (!loaded) {
            cached = storage { readStored() }
            loaded = true
        }
        cached
    }

    suspend fun save(session: Session) = lock.withLock {
        storage {
            secure.put(KEY_TOKEN, session.token)
            secure.put(KEY_USER, session.userId.toString())
        }
        cached = session
        loaded = true
    }

    suspend fun clear() = lock.withLock {
        cached = null
        loaded = true
        // Removing is best effort: the in-memory session is already gone, so the app is signed out.
        runCatching {
            secure.remove(KEY_TOKEN)
            secure.remove(KEY_USER)
        }.exceptionOrNull()?.let { if (it is CancellationException) throw it }
    }

    private suspend fun readStored(): Session? {
        val token = secure.get(KEY_TOKEN) ?: return null
        val userId = secure.get(KEY_USER)?.toIntOrNull() ?: return null
        return Session(token, userId)
    }

    private suspend fun <T> storage(block: suspend () -> T): T = try {
        block()
    } catch (e: CancellationException) {
        throw e
    } catch (e: AppError) {
        throw e
    } catch (e: Throwable) {
        throw AppError.Storage("Could not access secure storage on this device.", e)
    }

    companion object {
        // Same keys as the Flutter app.
        const val KEY_TOKEN = "auth_token"
        const val KEY_USER = "user_id"
    }
}
