package com.osiris.shared.data.exercise

import app.cash.sqldelight.db.SqlDriver
import com.osiris.shared.core.error.AppError
import com.osiris.shared.core.error.Outcome
import com.osiris.shared.core.error.outcomeOf
import com.osiris.shared.core.logging.Logger
import com.osiris.shared.data.network.api.ExerciseApi
import com.osiris.shared.data.platform.writeTextFile
import com.osiris.shared.domain.exercise.ExerciseCatalog
import com.osiris.shared.domain.exercise.PoseRecording
import com.osiris.shared.domain.exercise.SessionSummary
import com.osiris.shared.domain.model.ExerciseHistory
import com.osiris.shared.domain.model.SetOutcome
import com.osiris.shared.domain.model.SyncResult
import com.osiris.shared.domain.repository.ExerciseRepository
import com.russhwolf.settings.Settings
import kotlin.coroutines.cancellation.CancellationException
import kotlin.time.Clock
import kotlin.time.Instant
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonObject

/**
 * Camera-verified exercises: catalog, consent, the local set store, and upload sync.
 *
 * The database opens lazily on first use. If it cannot open (full disk, corrupt file), the
 * exercises still list and count from the bundled catalog; only saving fails, with a message.
 */
class ExerciseRepositoryImpl(
    private val api: ExerciseApi,
    private val openDatabase: () -> SqlDriver,
    private val settings: Settings,
    private val currentUserId: () -> Int?,
    private val io: CoroutineDispatcher,
    private val background: CoroutineScope,
    private val logger: Logger,
    private val recordingsDir: String?,
    private val bundledCatalog: () -> String = { BundledCatalog.JSON },
    private val clock: Clock = Clock.System,
) : ExerciseRepository {
    private val openLock = Mutex()
    private val syncLock = Mutex()
    private var store: ExerciseStore? = null

    override suspend fun bindAccount(userId: Int?) {
        // The common case (same account at every launch) never opens the database: opening it on
        // each restore added about 200 ms to cold start in the Flutter app.
        if (userId != null && settings.getIntOrNull(KEY_OWNER) == userId) return
        val db = storeOrThrow()
        withContext(io) { db.forgetOtherUsers(userId) }
        if (userId == null) settings.remove(KEY_OWNER) else settings.putInt(KEY_OWNER, userId)
    }

    override suspend fun catalog(): Outcome<ExerciseCatalog> = outcomeOf {
        val db = storeOrNull()
        val cached = db?.let { withContext(io) { it.cachedCatalogJson() } }
        val catalog = cached?.let {
            try {
                ExerciseCatalog.parse(it)
            } catch (e: Exception) {
                logger.warn(TAG, "Cached catalog unreadable; using the bundled one", e)
                null
            }
        } ?: parseBundled()
        if (db != null) background.launch { refreshCatalog(db) }
        catalog
    }

    override suspend fun consent(): Boolean {
        val userId = currentUserId() ?: return false
        return try {
            val granted = api.consent().granted
            settings.putBoolean(consentKey(userId), granted)
            granted
        } catch (e: CancellationException) {
            throw e
        } catch (e: Throwable) {
            settings.getBoolean(consentKey(userId), false)
        }
    }

    override suspend fun setConsent(granted: Boolean, deleteData: Boolean): Outcome<Boolean> = outcomeOf {
        val userId = currentUserId() ?: throw AppError.Unauthorized()
        val now = api.setConsent(granted, deleteData).granted
        settings.putBoolean(consentKey(userId), now)
        if (!now && deleteData) storeOrNull()?.let { db -> withContext(io) { db.deleteUserSessions(userId) } }
        now
    }

    override suspend fun saveSet(summary: SessionSummary, startedAt: Instant): Outcome<SetOutcome> = outcomeOf {
        val userId = currentUserId() ?: throw AppError.Unauthorized()
        val db = storeOrThrow()
        try {
            withContext(io) { db.saveSession(summary, userId, startedAt, clock.now()) }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Throwable) {
            throw AppError.Storage("This set could not be saved on your phone.", e)
        }
        val result = try {
            flush(db, userId)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Throwable) {
            // Saved; a later pass uploads it.
            logger.warn(TAG, "Upload after save failed", e)
            SyncResult(0, 0, offline = true)
        }
        SetOutcome(uploaded = !result.offline && result.uploaded > 0, xpAwarded = result.xpAwarded)
    }

    override suspend fun history(): ExerciseHistory {
        val userId = currentUserId() ?: return ExerciseHistory.EMPTY
        val db = storeOrNull() ?: return ExerciseHistory.EMPTY
        return try {
            withContext(io) { ExerciseHistory(db.recent(userId), db.personalBests(userId)) }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Throwable) {
            logger.error(TAG, "History read failed", e)
            ExerciseHistory.EMPTY
        }
    }

    override suspend fun sync(): Boolean {
        val userId = currentUserId() ?: return false
        val db = storeOrNull() ?: return false
        return try {
            val uploaded = flush(db, userId).uploaded
            val changed = refreshOutcomes(db)
            uploaded > 0 || changed > 0
        } catch (e: CancellationException) {
            throw e
        } catch (e: Throwable) {
            logger.warn(TAG, "Sync failed", e)
            false
        }
    }

    override suspend fun saveRecording(recording: PoseRecording): Outcome<String> = outcomeOf {
        val dir = recordingsDir ?: throw AppError.Validation("Pose recording is off in this build.")
        val name = "${recording.exerciseKey}_${recording.recordedAt.toEpochMilliseconds()}.json"
        try {
            withContext(io) { writeTextFile(dir, name, recording.toJson()) }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Throwable) {
            throw AppError.Storage("The recording could not be saved.", e)
        }
    }

    /**
     * Uploads saved sets in recording order. Uploads are idempotent per set id, so a lost response
     * is safe to retry. Network trouble, 5xx, 429 and 401 keep the set for the next pass; any other
     * 4xx means the server will never accept the body, so retries stop.
     */
    internal suspend fun flush(db: ExerciseStore, userId: Int): SyncResult {
        if (!syncLock.tryLock()) return SyncResult(0, 0)
        try {
            var uploaded = 0
            var xp = 0
            for (s in withContext(io) { db.pending(userId) }) {
                try {
                    val out = api.submit(s.toUpload())
                    withContext(io) { db.markSynced(s.id, out.status, out.xpAwarded) }
                    uploaded++
                    xp += out.xpAwarded
                } catch (e: CancellationException) {
                    throw e
                } catch (e: AppError) {
                    val permanent = e is AppError.Http && e.isClientError && e.status != 429
                    withContext(io) { db.markFailed(s.id, describe(e), permanent) }
                    if (!permanent) return SyncResult(uploaded, xp, offline = e is AppError.Offline || e is AppError.Timeout)
                }
            }
            return SyncResult(uploaded, xp)
        } finally {
            syncLock.unlock()
        }
    }

    /** Pulls server outcomes for recent sets; returns how many local sets changed (0 offline). */
    internal suspend fun refreshOutcomes(db: ExerciseStore): Int = try {
        val sessions = api.history(limit = 50).sessions
        withContext(io) { db.applyServerResults(sessions) }
    } catch (e: CancellationException) {
        throw e
    } catch (e: AppError) {
        0
    }

    private suspend fun refreshCatalog(db: ExerciseStore) {
        try {
            val doc: JsonObject = api.catalog()
            val catalog = ExerciseCatalog.fromJson(doc)
            withContext(io) { db.cacheCatalog(catalog.rulesVersion, doc.toString(), clock.now()) }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Throwable) {
            logger.debug(TAG, "Catalog refresh skipped: ${e.message}")
        }
    }

    private fun parseBundled(): ExerciseCatalog = try {
        ExerciseCatalog.parse(bundledCatalog())
    } catch (e: Exception) {
        throw AppError.Unexpected(e)
    }

    private suspend fun storeOrNull(): ExerciseStore? = try {
        storeOrThrow()
    } catch (e: AppError.Storage) {
        null
    }

    private suspend fun storeOrThrow(): ExerciseStore = openLock.withLock {
        store ?: try {
            withContext(io) { ExerciseStore(openDatabase()) }.also { store = it }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Throwable) {
            logger.error(TAG, "Exercise database unavailable", e)
            throw AppError.Storage("Exercise history is unavailable on this phone.", e)
        }
    }

    private fun describe(e: AppError): String = when (e) {
        is AppError.Http -> "HTTP ${e.status}"
        is AppError.Unauthorized -> "HTTP 401"
        is AppError.Offline, is AppError.Timeout -> "network"
        else -> e::class.simpleName ?: "error"
    }

    private fun consentKey(userId: Int) = "osiris.exercise_consent.$userId"

    companion object {
        private const val TAG = "OsirisExercise"
        const val KEY_OWNER = "osiris.exercise_owner.v1"
    }
}
