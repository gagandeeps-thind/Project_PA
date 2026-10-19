package com.osiris.shared.data.repository

import com.osiris.shared.core.error.AppError
import com.osiris.shared.core.error.Outcome
import com.osiris.shared.core.error.outcomeOf
import com.osiris.shared.core.logging.Logger
import com.osiris.shared.data.network.api.AuthApi
import com.osiris.shared.data.network.api.MeApi
import com.osiris.shared.domain.model.Registration
import com.osiris.shared.domain.model.Session
import com.osiris.shared.domain.model.UserProfile
import com.osiris.shared.domain.repository.AccountScoped
import com.osiris.shared.domain.repository.AuthRepository
import com.osiris.shared.domain.repository.AuthState
import com.russhwolf.settings.Settings
import kotlin.coroutines.cancellation.CancellationException
import kotlin.time.Clock
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/**
 * Players only: merchants and admins have their own apps and are refused here.
 *
 * Every account change (sign in, sign up, restore, sign out) is passed to [accountScoped], so
 * one person's queued run or exercise history never shows to the next person on the phone.
 *
 * Unlike the Flutter app, an offline start does not sign the player out: the last profile is
 * cached (it is not secret) and the session is dropped only when the server says it is invalid.
 */
class AuthRepositoryImpl(
    private val auth: AuthApi,
    private val me: MeApi,
    private val session: SessionStore,
    private val settings: Settings,
    private val installId: InstallId,
    private val accountScoped: List<AccountScoped>,
    private val logger: Logger,
    private val clock: Clock = Clock.System,
) : AuthRepository {
    private val json = Json { ignoreUnknownKeys = true }
    private val _state = MutableStateFlow<AuthState>(AuthState.Restoring)
    override val state: StateFlow<AuthState> = _state.asStateFlow()

    /** The signed-in player's id, or null. */
    val currentUserId: Int? get() = (_state.value as? AuthState.SignedIn)?.user?.id

    override suspend fun restore() {
        val stored = try {
            session.current()
        } catch (e: CancellationException) {
            throw e
        } catch (e: Throwable) {
            logger.warn(TAG, "Session restore could not read secure storage", e)
            null
        }
        if (stored == null) {
            signedOut()
            return
        }
        try {
            val user = auth.user(stored.userId)
            if (!user.isPlayer) {
                signOutLocally()
                return
            }
            becomeSignedIn(user)
        } catch (e: CancellationException) {
            throw e
        } catch (e: AppError) {
            val cachedUser = cachedProfile()?.takeIf { it.id == stored.userId }
            if (e.isTransient && cachedUser != null) {
                logger.info(TAG, "Offline start; using the cached profile")
                becomeSignedIn(cachedUser)
            } else {
                signOutLocally()
            }
        } catch (e: Throwable) {
            logger.error(TAG, "Session restore failed", e)
            signOutLocally()
        }
    }

    override suspend fun login(email: String, password: String): Outcome<UserProfile> = outcomeOf {
        if (!email.contains('@') || password.isEmpty()) throw AppError.Validation("Enter your email and password.")
        val response = auth.login(email.trim(), password, clock.now())
        if (response.role != UserProfile.ROLE_PLAYER) {
            throw AppError.Validation(
                "This app is for Osiris players only. Merchants and admins should use their dedicated apps.",
            )
        }
        adopt(Session(response.accessToken, response.userId))
    }

    override suspend fun register(registration: Registration): Outcome<UserProfile> = outcomeOf {
        registration.validate().values.firstOrNull()?.let { throw AppError.Validation(it) }
        val response = auth.register(registration, utcOffsetMinutes(clock.now()), installId.get())
        val user = adopt(Session(response.accessToken, response.profile.userId))
        // The account exists either way; a failure here only means onboarding shows again.
        try {
            me.updateProfile(buildJsonObject { put("onboarding_completed", JsonPrimitive(true)) })
        } catch (e: CancellationException) {
            throw e
        } catch (e: Throwable) {
            logger.warn(TAG, "Could not mark onboarding completed", e)
        }
        user
    }

    override suspend fun signOutEverywhere(): Outcome<Unit> = outcomeOf {
        val userId = currentUserId ?: throw AppError.Unauthorized()
        val fresh = auth.revokeOtherSessions()
        adopt(Session(fresh.accessToken, userId))
        Unit
    }

    override suspend fun logout() = signOutLocally()

    override suspend fun onSessionExpired() {
        if (_state.value is AuthState.SignedIn) logger.info(TAG, "Session expired")
        signOutLocally()
    }

    private suspend fun adopt(new: Session): UserProfile {
        session.save(new)
        val user = try {
            auth.user(new.userId)
        } catch (e: Throwable) {
            session.clear()
            throw e
        }
        becomeSignedIn(user)
        return user
    }

    private suspend fun becomeSignedIn(user: UserProfile) {
        bind(user.id)
        settings.putString(KEY_PROFILE, json.encodeToString(UserProfile.serializer(), user))
        _state.value = AuthState.SignedIn(user)
    }

    private suspend fun signOutLocally() {
        session.clear()
        settings.remove(KEY_PROFILE)
        signedOut()
    }

    private suspend fun signedOut() {
        bind(null)
        _state.value = AuthState.SignedOut
    }

    private suspend fun bind(userId: Int?) {
        for (scoped in accountScoped) {
            try {
                scoped.bindAccount(userId)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Throwable) {
                // Never blocks signing in; the data is re-checked at the next account change.
                logger.error(TAG, "Account binding failed", e)
            }
        }
    }

    private fun cachedProfile(): UserProfile? = settings.getStringOrNull(KEY_PROFILE)?.let {
        runCatching { json.decodeFromString(UserProfile.serializer(), it) }.getOrNull()
    }

    companion object {
        private const val TAG = "OsirisAuth"
        const val KEY_PROFILE = "osiris.user_profile.v1"
    }
}
