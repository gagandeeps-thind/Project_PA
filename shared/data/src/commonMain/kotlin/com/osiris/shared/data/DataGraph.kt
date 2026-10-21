package com.osiris.shared.data

import com.osiris.shared.core.config.AppConfig
import com.osiris.shared.data.exercise.ExerciseRepositoryImpl
import com.osiris.shared.data.network.ApiClient
import com.osiris.shared.data.network.api.AuthApi
import com.osiris.shared.data.network.api.ChallengeApi
import com.osiris.shared.data.network.api.CommunityApi
import com.osiris.shared.data.network.api.ExerciseApi
import com.osiris.shared.data.network.api.MeApi
import com.osiris.shared.data.network.api.RunApi
import com.osiris.shared.data.repository.AuthRepositoryImpl
import com.osiris.shared.data.repository.ChallengeRepositoryImpl
import com.osiris.shared.data.repository.DeviceSetupRepositoryImpl
import com.osiris.shared.data.repository.CommunityRepositoryImpl
import com.osiris.shared.data.repository.InstallId
import com.osiris.shared.data.repository.PlayerRepositoryImpl
import com.osiris.shared.data.repository.PrivacyRepositoryImpl
import com.osiris.shared.data.repository.RunRepositoryImpl
import com.osiris.shared.data.repository.SessionStore
import com.osiris.shared.data.storage.PlatformDependencies
import com.osiris.shared.domain.repository.AuthRepository
import com.osiris.shared.domain.repository.ChallengeRepository
import com.osiris.shared.domain.repository.CommunityRepository
import com.osiris.shared.domain.repository.DeviceSetupRepository
import com.osiris.shared.domain.repository.ExerciseRepository
import com.osiris.shared.domain.repository.PlayerRepository
import com.osiris.shared.domain.repository.PrivacyRepository
import com.osiris.shared.domain.repository.RunRepository
import kotlin.time.Clock
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.IO
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel

/**
 * Wires the data layer once per process. Apps build it from their [PlatformDependencies]; tests
 * pass fakes (a Ktor MockEngine, in-memory settings and SQLite).
 *
 * Plain constructor injection, no DI framework: the graph is small, compile-checked, and reads
 * the same on Android and iOS.
 */
class DataGraph(
    config: AppConfig,
    platform: PlatformDependencies,
    clock: Clock = Clock.System,
    io: CoroutineDispatcher = Dispatchers.IO,
) {
    /** Outlives screens: background catalog refreshes and uploads. */
    val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    private val session = SessionStore(platform.secureStore)

    val api = ApiClient(config, platform.httpEngine, session, platform.logger, onUnauthorized = { authImpl.onSessionExpired() })

    private val me = MeApi(api)
    private val challengeApi = ChallengeApi(api)
    private val installId = InstallId(platform.settings) { id -> me.track("app_installed", id, emptyMap()) }

    private val runImpl = RunRepositoryImpl(RunApi(api), platform.settings, { authImpl.currentUserId }, platform.logger)

    private val exerciseImpl = ExerciseRepositoryImpl(
        api = ExerciseApi(api),
        openDatabase = platform.openDatabase,
        settings = platform.settings,
        currentUserId = { authImpl.currentUserId },
        io = io,
        background = scope,
        logger = platform.logger,
        recordingsDir = platform.recordingsDir.takeIf { config.features.poseRecording },
        clock = clock,
    )

    private val authImpl: AuthRepositoryImpl = AuthRepositoryImpl(
        auth = AuthApi(api),
        me = me,
        session = session,
        settings = platform.settings,
        installId = installId,
        accountScoped = listOf(runImpl, exerciseImpl),
        logger = platform.logger,
        clock = clock,
    )

    val auth: AuthRepository get() = authImpl
    val runs: RunRepository get() = runImpl
    val exercises: ExerciseRepository get() = exerciseImpl
    val player: PlayerRepository = PlayerRepositoryImpl(me, installId, platform.logger, clock)
    val challenges: ChallengeRepository = ChallengeRepositoryImpl(challengeApi)
    val communities: CommunityRepository = CommunityRepositoryImpl(CommunityApi(api), challengeApi)
    val privacy: PrivacyRepository = PrivacyRepositoryImpl(me, authImpl)
    val deviceSetup: DeviceSetupRepository = DeviceSetupRepositoryImpl(platform.settings)

    fun close() {
        scope.cancel()
        api.close()
    }
}
