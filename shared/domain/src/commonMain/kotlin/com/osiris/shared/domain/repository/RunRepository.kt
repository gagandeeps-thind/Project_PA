package com.osiris.shared.domain.repository

import com.osiris.shared.core.error.Outcome
import com.osiris.shared.domain.model.RunResult
import com.osiris.shared.domain.run.ActiveRun
import com.osiris.shared.domain.run.LocationFix
import com.osiris.shared.domain.run.Sport
import kotlin.time.Instant
import kotlinx.coroutines.flow.StateFlow

/**
 * Run recording with a durable, ordered upload queue (PRD-003): an app restart or a network
 * outage never loses route points.
 */
interface RunRepository : AccountScoped {
    /** The run being recorded, restored after an app restart; null when none. */
    val active: StateFlow<ActiveRun?>

    /** True while the last upload attempt failed for lack of network. */
    val offline: StateFlow<Boolean>

    /** Creates and starts a run on the server, then records locally. */
    suspend fun start(challengeId: Int?, now: Instant, sport: Sport = Sport.RUN, autoPause: Boolean = true): Outcome<ActiveRun>

    /** Queues one GPS fix and uploads in batches. No-op without an active run. */
    suspend fun addFix(fix: LocationFix, now: Instant)

    /** Uploads everything queued. True when the queue is empty afterwards. */
    suspend fun flush(): Outcome<Boolean>

    /** Uploads the rest and finishes the run. Fails with [com.osiris.shared.core.error.AppError.Offline] when points are still queued. */
    suspend fun finish(now: Instant): Outcome<RunResult>

    /** Deletes the run from this phone. */
    suspend fun discard()
}
