package com.osiris.shared.presentation

import com.osiris.shared.core.error.AppError
import com.osiris.shared.core.error.Outcome
import com.osiris.shared.domain.exercise.ExerciseCatalog
import com.osiris.shared.domain.exercise.ExerciseSpec
import com.osiris.shared.domain.model.ChallengeSummary
import com.osiris.shared.domain.run.LocationFix
import kotlin.time.Clock
import kotlin.time.Instant
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime

/** The exercise a camera screen opens: the spec and catalog, or why it cannot open. */
class ExerciseLoad(val spec: ExerciseSpec?, val catalog: ExerciseCatalog?, val error: String?)

/**
 * Calls Swift cannot make cleanly against the exported API: building `kotlin.time.Instant`,
 * reading `Outcome`, and reaching repositories in the non-exported data module.
 * Swift calls it as `IosSupport.shared.…`.
 */
object IosSupport {
    /**
     * A Core Location fix. Negative accuracy or speed means unknown, as CLLocation reports them;
     * [measuredAtEpochMs] is `CLLocation.timestamp`, so delivery jitter never shifts route points.
     */
    fun locationFix(
        lat: Double,
        lng: Double,
        accuracyM: Double,
        speedMps: Double,
        altitudeM: Double,
        hasAltitude: Boolean,
        measuredAtEpochMs: Long,
    ): LocationFix = LocationFix(
        lat = lat,
        lng = lng,
        accuracyM = accuracyM.takeIf { it >= 0 },
        speedMps = speedMps.takeIf { it >= 0 },
        altitudeM = if (hasAltitude) altitudeM else null,
        at = Instant.fromEpochMilliseconds(measuredAtEpochMs),
    )

    fun locationOff(): AppError = AppError.Permission("location", "Location is off for Osiris. Allow it in Settings to record runs.")

    fun cameraOff(): AppError = AppError.Permission("camera", "Camera access is off for Osiris. Allow it in Settings to count reps.")

    fun cameraUnavailable(): AppError = AppError.Validation("The camera could not start. Close other camera apps and try again.")

    /** `2d 3h left`, as of now. */
    fun closesIn(c: ChallengeSummary): String = c.closesIn(Clock.System.now())

    /** `2026-10-19 18:30` in the phone's time zone, or null when the challenge has no close time. */
    fun closesAtLocal(c: ChallengeSummary): String? = c.closesAt?.let(::localMinute)

    /** `2026-10-19 18:30` in the phone's time zone. */
    fun localMinute(at: Instant): String {
        val t = at.toLocalDateTime(TimeZone.currentSystemDefault())
        fun two(v: Int) = v.toString().padStart(2, '0')
        return "${t.year}-${two(t.month.ordinal + 1)}-${two(t.day)} ${two(t.hour)}:${two(t.minute)}"
    }

    /** The catalog is cached by the repository (bundled copy offline), so this returns at once. */
    suspend fun loadExercise(graph: AppGraph, key: String): ExerciseLoad =
        when (val c = graph.data.exercises.catalog()) {
            is Outcome.Failure -> ExerciseLoad(null, null, c.error.userMessage)
            is Outcome.Success -> c.value.byKey(key)?.let { ExerciseLoad(it, c.value, null) }
                ?: ExerciseLoad(null, null, "This exercise is not available.")
        }
}
