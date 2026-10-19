package com.osiris.player.platform.location

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.os.Looper
import android.os.SystemClock
import androidx.core.content.ContextCompat
import com.google.android.gms.location.LocationCallback
import com.google.android.gms.location.LocationRequest
import com.google.android.gms.location.LocationResult
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import com.osiris.shared.core.error.AppError
import com.osiris.shared.domain.run.LocationFix
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.tasks.await
import kotlin.time.Clock
import kotlin.time.Duration.Companion.nanoseconds
import kotlin.time.Instant

/**
 * Fused location as a flow of [LocationFix]. High accuracy, one fix a second at most and only
 * after 5 m of movement, the same settings as the Flutter app.
 *
 * Updates run on the main looper, so they keep arriving while [RunTrackingService] holds the
 * process in the foreground with the screen off.
 */
class LocationClient(context: Context) {
    private val app = context.applicationContext
    private val fused = LocationServices.getFusedLocationProviderClient(app)

    fun hasPermission(): Boolean =
        ContextCompat.checkSelfPermission(app, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED

    /** Fails with [AppError.Permission] when fine location is not granted. */
    @SuppressLint("MissingPermission")
    fun fixes(): Flow<LocationFix> = callbackFlow {
        if (!hasPermission()) {
            close(LocationUnavailable(permissionError()))
            return@callbackFlow
        }
        val request = LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, INTERVAL_MS)
            .setMinUpdateIntervalMillis(INTERVAL_MS)
            .setMinUpdateDistanceMeters(DISTANCE_FILTER_M)
            .build()
        val callback = object : LocationCallback() {
            override fun onLocationResult(result: LocationResult) {
                for (l in result.locations) {
                    trySend(
                        LocationFix(
                            lat = l.latitude,
                            lng = l.longitude,
                            accuracyM = if (l.hasAccuracy()) l.accuracy.toDouble() else null,
                            speedMps = if (l.hasSpeed()) l.speed.toDouble() else null,
                            altitudeM = if (l.hasAltitude()) l.altitude else null,
                            at = l.measuredAt(),
                        ),
                    )
                }
            }
        }
        // A fast first position from the cache, so the map centres before the first live fix.
        runCatching { fused.lastLocation.await() }.getOrNull()?.let {
            trySend(
                LocationFix(
                    lat = it.latitude,
                    lng = it.longitude,
                    accuracyM = if (it.hasAccuracy()) it.accuracy.toDouble() else null,
                    at = it.measuredAt(),
                ),
            )
        }
        try {
            fused.requestLocationUpdates(request, callback, Looper.getMainLooper()).await()
        } catch (e: SecurityException) {
            close(LocationUnavailable(permissionError()))
        } catch (e: Exception) {
            close(LocationUnavailable(AppError.Unexpected(e)))
        }
        awaitClose { fused.removeLocationUpdates(callback) }
    }

    /**
     * When the fix was measured, from its monotonic age rather than [Location.getTime], so a wrong
     * device or GNSS clock cannot shift points against the run's start.
     */
    private fun Location.measuredAt(): Instant {
        val age = (SystemClock.elapsedRealtimeNanos() - elapsedRealtimeNanos).coerceAtLeast(0)
        return Clock.System.now() - age.nanoseconds
    }

    companion object {
        const val INTERVAL_MS = 1_000L
        const val DISTANCE_FILTER_M = 5f

        fun permissionError() = AppError.Permission(
            Manifest.permission.ACCESS_FINE_LOCATION,
            "Location is off for Osiris. Allow it in Settings to record runs.",
        )
    }
}

/** Ends a [LocationClient.fixes] flow with the error to show. */
class LocationUnavailable(val error: AppError) : Exception(error.userMessage)
