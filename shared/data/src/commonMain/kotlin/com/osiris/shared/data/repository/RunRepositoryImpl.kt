package com.osiris.shared.data.repository

import com.osiris.shared.core.error.AppError
import com.osiris.shared.core.error.Outcome
import com.osiris.shared.core.error.outcomeOf
import com.osiris.shared.core.logging.Logger
import com.osiris.shared.data.network.api.RunApi
import com.osiris.shared.domain.model.RunResult
import com.osiris.shared.domain.repository.RunRepository
import com.osiris.shared.domain.run.ActiveRun
import com.osiris.shared.domain.run.AutoPause
import com.osiris.shared.domain.run.LocationFix
import com.osiris.shared.domain.run.Sport
import com.russhwolf.settings.Settings
import kotlin.coroutines.cancellation.CancellationException
import kotlin.time.Instant
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.serialization.json.Json

/**
 * Durable, ordered upload queue for route points (PRD-003).
 *
 * Points get contiguous sequence numbers at capture time and stay in [Settings] until the
 * server acknowledges them. If an upload's response is lost after the server stored it, the next
 * attempt gets a 409; the queue then asks the server how many points it holds and drops those.
 */
class RunRepositoryImpl(
    private val api: RunApi,
    private val settings: Settings,
    private val currentUserId: () -> Int?,
    private val logger: Logger,
) : RunRepository {
    private val json = Json { ignoreUnknownKeys = true }
    private val state = Mutex()
    private val upload = Mutex()
    private val _active = MutableStateFlow(load())
    private val _offline = MutableStateFlow(false)

    override val active: StateFlow<ActiveRun?> = _active.asStateFlow()
    override val offline: StateFlow<Boolean> = _offline.asStateFlow()

    override suspend fun bindAccount(userId: Int?) {
        state.withLock {
            val run = _active.value
            if (run != null && (userId == null || run.userId != userId)) clearLocked()
        }
    }

    override suspend fun start(challengeId: Int?, now: Instant, sport: Sport, autoPause: AutoPause): Outcome<ActiveRun> = outcomeOf {
        val userId = currentUserId() ?: throw AppError.Unauthorized()
        if (_active.value != null) throw AppError.Validation("A run is already being recorded.")
        val created = api.create(now, sport.wire)
        api.start(created.id, now)
        val run = ActiveRun(
            runId = created.id,
            userId = userId,
            startedAt = now,
            challengeId = challengeId,
            sport = sport.wire,
            autoPause = autoPause.on,
            autoPauseMps = if (autoPause.on) autoPause.mps else ActiveRun.MOVING_MIN_MPS,
        )
        state.withLock { save(run) }
        _offline.value = false
        run
    }

    override suspend fun addFix(fix: LocationFix, now: Instant) {
        val pending = state.withLock {
            val run = _active.value ?: return
            val next = run.withFix(fix, now)
            save(next)
            next.pending.size
        }
        if (pending >= FLUSH_AT) {
            flush().errorOrNull()?.let { logger.warn(TAG, "Point upload failed: ${it.userMessage}") }
        }
    }

    override suspend fun flush(): Outcome<Boolean> = outcomeOf {
        // One upload pass at a time; a second caller just reports the current state.
        if (!upload.tryLock()) return@outcomeOf _active.value?.pending.isNullOrEmpty()
        try {
            drain()
        } finally {
            upload.unlock()
        }
    }

    override suspend fun finish(now: Instant): Outcome<RunResult> = outcomeOf {
        val run = _active.value ?: throw AppError.Validation("No run is being recorded.")
        // Waits for a background upload instead of skipping it, which would report "offline".
        if (!upload.withLock { drain() }) throw AppError.Offline()
        val result = api.finish(run.runId, now, "run-${run.runId}-finish", run.pauseBelowMps)
        state.withLock { clearLocked() }
        result
    }

    override suspend fun discard() = state.withLock { clearLocked() }

    /** Returns true when the queue is empty afterwards; false when offline (points stay queued). */
    private suspend fun drain(): Boolean {
        while (true) {
            val run = _active.value ?: return true
            if (run.pending.isEmpty()) {
                _offline.value = false
                return true
            }
            val batch = run.pending.take(BATCH)
            try {
                api.appendPoints(run.runId, batch)
                val last = batch.last().sequence
                state.withLock { update { r -> r.copy(pending = r.pending.filter { it.sequence > last }) } }
            } catch (e: CancellationException) {
                throw e
            } catch (e: AppError) {
                when {
                    e is AppError.Http && e.status == 409 -> {
                        val stored = api.run(run.runId).pointCount
                        val before = run.pending.size
                        val after = state.withLock {
                            update { r -> r.copy(pending = r.pending.filter { it.sequence >= stored }) }
                        }
                        if (after == before) throw e
                    }
                    e is AppError.Offline || e is AppError.Timeout -> {
                        _offline.value = true
                        return false
                    }
                    else -> throw e
                }
            }
        }
    }

    /** Applies [change] to the active run, persists it, and returns the new pending count. */
    private fun update(change: (ActiveRun) -> ActiveRun): Int {
        val run = _active.value ?: return 0
        val next = change(run)
        save(next)
        return next.pending.size
    }

    private fun save(run: ActiveRun) {
        try {
            settings.putString(KEY, json.encodeToString(ActiveRun.serializer(), run))
        } catch (e: Throwable) {
            throw AppError.Storage("Could not save the run on this phone.", e)
        }
        _active.value = run
    }

    private fun clearLocked() {
        settings.remove(KEY)
        _active.value = null
        _offline.value = false
    }

    private fun load(): ActiveRun? {
        val raw = settings.getStringOrNull(KEY) ?: return null
        return try {
            json.decodeFromString(ActiveRun.serializer(), raw)
        } catch (e: Throwable) {
            // Written by an incompatible version; the points cannot be uploaded safely anyway.
            logger.warn(TAG, "Discarding an unreadable saved run", e)
            settings.remove(KEY)
            null
        }
    }

    companion object {
        private const val TAG = "OsirisRun"
        const val KEY = "osiris.active_run.v1"
        const val BATCH = 400
        /** Upload once this many points are queued, so a crash loses at most a few seconds. */
        const val FLUSH_AT = 5
    }
}
