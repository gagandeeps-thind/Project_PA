package com.osiris.player.platform.health

import android.content.Context
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.PermissionController
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.DistanceRecord
import androidx.health.connect.client.records.ExerciseSessionRecord
import androidx.health.connect.client.records.HeartRateRecord
import androidx.health.connect.client.records.PowerRecord
import androidx.health.connect.client.records.Record
import androidx.health.connect.client.records.SpeedRecord
import androidx.health.connect.client.request.AggregateRequest
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import com.osiris.shared.core.error.Outcome
import com.osiris.shared.core.error.outcomeOf
import com.osiris.shared.domain.model.NewTrainingSession
import com.osiris.shared.domain.model.TrainingSeries
import com.osiris.shared.domain.repository.TrainingRepository
import com.osiris.shared.domain.training.TrainingRecorder
import java.time.Duration
import java.time.Instant
import kotlin.reflect.KClass

/** Whether Health Connect can be used on this phone. */
enum class HealthAvailability { READY, NOT_INSTALLED, UNSUPPORTED }

/**
 * Imports past workouts from Health Connect (Samsung Health, Fitbit, Google Fit and watch apps
 * sync into it) as Train sessions. Each record is uploaded once: its Health Connect id is the
 * session's client id, so importing again changes nothing.
 */
class HealthConnectImporter(context: Context, private val training: TrainingRepository) {
    private val app = context.applicationContext

    val permissions: Set<String> = setOf(
        ExerciseSessionRecord::class, HeartRateRecord::class, SpeedRecord::class, PowerRecord::class, DistanceRecord::class,
    ).map { HealthPermission.getReadPermission(it) }.toSet()

    /** The system screen that asks for [permissions]. */
    val permissionContract = PermissionController.createRequestPermissionResultContract()

    fun availability(): HealthAvailability = when (HealthConnectClient.getSdkStatus(app)) {
        HealthConnectClient.SDK_AVAILABLE -> HealthAvailability.READY
        HealthConnectClient.SDK_UNAVAILABLE_PROVIDER_UPDATE_REQUIRED -> HealthAvailability.NOT_INSTALLED
        else -> HealthAvailability.UNSUPPORTED
    }

    suspend fun granted(): Boolean =
        client().permissionController.getGrantedPermissions().containsAll(permissions)

    /** Uploads the last [days] of workouts; returns how many sessions were saved. */
    suspend fun import(days: Long = DEFAULT_DAYS): Outcome<Int> = outcomeOf {
        val hc = client()
        val now = Instant.now()
        val sessions = hc.readRecords(
            ReadRecordsRequest(ExerciseSessionRecord::class, TimeRangeFilter.between(now.minus(Duration.ofDays(days)), now)),
        ).records
        var saved = 0
        for (s in sessions) {
            val key = ACTIVITY_KEYS[s.exerciseType] ?: continue
            val range = TimeRangeFilter.between(s.startTime, s.endTime)
            val durationS = Duration.between(s.startTime, s.endTime).seconds.toDouble()
            if (durationS < 1) continue
            fun t(at: Instant) = Duration.between(s.startTime, at).toMillis() / MS
            val hr = read(hc, HeartRateRecord::class, range).flatMap { r -> r.samples.map { listOf(t(it.time), it.beatsPerMinute.toDouble()) } }
            val speed = read(hc, SpeedRecord::class, range).flatMap { r -> r.samples.map { listOf(t(it.time), it.speed.inMetersPerSecond) } }
            val power = read(hc, PowerRecord::class, range).flatMap { r -> r.samples.map { listOf(t(it.time), it.power.inWatts) } }
            val distance = hc.aggregate(AggregateRequest(setOf(DistanceRecord.DISTANCE_TOTAL), range))[DistanceRecord.DISTANCE_TOTAL]
            val body = NewTrainingSession(
                clientSessionId = "hc-${s.metadata.id}".take(CLIENT_ID_MAX), activityKey = key, mode = "train",
                source = "health_connect", startedAt = s.startTime.toString(), durationS = durationS,
                distanceM = distance?.inMeters ?: 0.0,
                series = TrainingSeries(hr = cap(hr), power = cap(power), speed = cap(speed)),
            )
            // An implausible record (a watch glitch) is skipped rather than stopping the import.
            if (training.upload(body) is Outcome.Success) saved++
        }
        saved
    }

    private fun client() = HealthConnectClient.getOrCreate(app)

    private suspend fun <T : Record> read(hc: HealthConnectClient, type: KClass<T>, range: TimeRangeFilter): List<T> =
        hc.readRecords(ReadRecordsRequest(type, range)).records

    private fun cap(points: List<List<Double>>) =
        TrainingRecorder.downsample(points.sortedBy { it[0] }, TrainingRecorder.MAX_POINTS)

    private companion object {
        const val DEFAULT_DAYS = 30L
        const val MS = 1000.0
        const val CLIENT_ID_MAX = 64

        val ACTIVITY_KEYS = mapOf(
            ExerciseSessionRecord.EXERCISE_TYPE_RUNNING to "run",
            ExerciseSessionRecord.EXERCISE_TYPE_RUNNING_TREADMILL to "run",
            ExerciseSessionRecord.EXERCISE_TYPE_WALKING to "walk",
            ExerciseSessionRecord.EXERCISE_TYPE_HIKING to "hike",
            ExerciseSessionRecord.EXERCISE_TYPE_BIKING to "cycle",
            ExerciseSessionRecord.EXERCISE_TYPE_BIKING_STATIONARY to "indoor_cycle",
            ExerciseSessionRecord.EXERCISE_TYPE_SWIMMING_POOL to "swim",
            ExerciseSessionRecord.EXERCISE_TYPE_SWIMMING_OPEN_WATER to "swim",
            ExerciseSessionRecord.EXERCISE_TYPE_ROWING to "row",
            ExerciseSessionRecord.EXERCISE_TYPE_ROWING_MACHINE to "row",
            ExerciseSessionRecord.EXERCISE_TYPE_ELLIPTICAL to "elliptical",
            ExerciseSessionRecord.EXERCISE_TYPE_STAIR_CLIMBING to "stairs",
            ExerciseSessionRecord.EXERCISE_TYPE_STAIR_CLIMBING_MACHINE to "stairs",
            ExerciseSessionRecord.EXERCISE_TYPE_HIGH_INTENSITY_INTERVAL_TRAINING to "hiit",
            ExerciseSessionRecord.EXERCISE_TYPE_STRENGTH_TRAINING to "strength",
            ExerciseSessionRecord.EXERCISE_TYPE_WEIGHTLIFTING to "strength",
            ExerciseSessionRecord.EXERCISE_TYPE_YOGA to "yoga",
        )
    }
}
