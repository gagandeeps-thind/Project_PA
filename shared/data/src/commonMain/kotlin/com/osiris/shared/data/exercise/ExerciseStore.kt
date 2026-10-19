package com.osiris.shared.data.exercise

import app.cash.sqldelight.db.SqlDriver
import com.osiris.shared.core.util.newHexId
import com.osiris.shared.data.db.Exercise_sessions
import com.osiris.shared.data.db.OsirisDatabase
import com.osiris.shared.domain.exercise.SessionSummary
import com.osiris.shared.domain.exercise.Verdict
import com.osiris.shared.domain.model.ServerExerciseSession
import com.osiris.shared.domain.model.StoredSession
import com.osiris.shared.domain.model.SyncState
import kotlin.time.Instant
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.builtins.serializer
import kotlinx.serialization.json.Json

/**
 * On-device store for the exercise feature, so counting, history and personal bests work offline
 * and instantly. Camera frames and landmarks are never stored; only set summaries and rep timings.
 * Calls are blocking; [ExerciseRepositoryImpl] runs them off the main thread.
 */
class ExerciseStore(private val driver: SqlDriver) {
    private val db = OsirisDatabase(driver)
    private val q = db.exerciseQueries
    private val reasons = ListSerializer(String.serializer())

    fun close() = driver.close()

    fun cachedCatalogJson(): String? = q.cachedCatalog().executeAsOneOrNull()

    fun cacheCatalog(rulesVersion: String, json: String, now: Instant) =
        q.cacheCatalog(rulesVersion, json, now.toEpochMilliseconds())

    /** Saves a set and its reps in one transaction; returns the set's id (the upload's idempotency key). */
    fun saveSession(s: SessionSummary, userId: Int, startedAt: Instant, now: Instant, id: String = newHexId()): String {
        db.transaction {
            q.insertSession(
                id = id,
                user_id = userId.toLong(),
                exercise_key = s.exerciseKey,
                rules_version = s.rulesVersion,
                started_at = startedAt.toEpochMilliseconds(),
                duration_s = s.durationS,
                reps_attempted = s.repsAttempted.toLong(),
                reps_valid = s.repsValid.toLong(),
                hold_s = s.holdS,
                form_score = s.formScore,
                verdict = s.verdict.wire,
                reasons_json = Json.encodeToString(reasons, s.reasons),
                created_at = now.toEpochMilliseconds(),
            )
            for (r in s.reps) {
                q.insertRep(id, r.index.toLong(), r.startMs, r.durationMs, r.peakValue, if (r.valid) 1 else 0, r.reason)
            }
        }
        return id
    }

    fun pending(userId: Int): List<StoredSession> = withReps(q.pendingSessions(userId.toLong()).executeAsList())

    fun recent(userId: Int, limit: Int = 20): List<StoredSession> =
        withReps(q.recentSessions(userId.toLong(), limit.toLong()).executeAsList())

    fun markSynced(id: String, serverStatus: String, xpAwarded: Int) = q.markSynced(serverStatus, xpAwarded.toLong(), id)

    /** A permanent refusal stops retries; a transient one only counts the attempt. */
    fun markFailed(id: String, error: String, permanent: Boolean) =
        q.markFailed(error, if (permanent) SyncState.FAILED.wire else SyncState.PENDING.wire, id)

    /** Applies later server decisions (an admin approving or rejecting a flagged set). Returns rows changed. */
    fun applyServerResults(results: List<ServerExerciseSession>): Int {
        var changed = 0L
        db.transaction {
            for (r in results) changed += q.applyServerResult(r.status, r.xpAwarded.toLong(), r.clientSessionId).value
        }
        return changed.toInt()
    }

    /** Best verified set per exercise: most valid reps, or longest hold. */
    fun personalBests(userId: Int): Map<String, Double> =
        q.personalBests(userId.toLong()).executeAsList().associate { it.exercise_key to (it.best ?: 0.0) }

    /** Erases one player's sets and reps (consent withdrawn with deletion). */
    fun deleteUserSessions(userId: Int) = q.deleteUserSessions(userId.toLong())

    /** Removes everything stored for other accounts; null removes everything. */
    fun forgetOtherUsers(userId: Int?) {
        if (userId == null) q.deleteAllSessions() else q.deleteOtherUsers(userId.toLong())
    }

    private fun withReps(rows: List<Exercise_sessions>): List<StoredSession> {
        if (rows.isEmpty()) return emptyList()
        val durations = q.validRepDurations(rows.map { it.id }).executeAsList()
            .groupBy({ it.session_id }, { it.duration_ms / 1000.0 })
        return rows.map { r ->
            StoredSession(
                id = r.id,
                userId = r.user_id.toInt(),
                exerciseKey = r.exercise_key,
                rulesVersion = r.rules_version,
                startedAt = Instant.fromEpochMilliseconds(r.started_at),
                durationS = r.duration_s,
                repsAttempted = r.reps_attempted.toInt(),
                repsValid = r.reps_valid.toInt(),
                holdS = r.hold_s,
                formScore = r.form_score,
                verdict = Verdict.fromWire(r.verdict),
                reasons = runCatching { Json.decodeFromString(reasons, r.reasons_json) }.getOrDefault(emptyList()),
                repDurationsS = durations[r.id].orEmpty(),
                syncState = SyncState.fromWire(r.sync_state),
                serverStatus = r.server_status,
                xpAwarded = r.xp_awarded.toInt(),
            )
        }
    }
}
