package osiris.fit.platform.location

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleService
import androidx.lifecycle.lifecycleScope
import com.osiris.shared.core.error.AppError
import com.osiris.shared.core.logging.platformLogger
import com.osiris.shared.domain.repository.RunRepository
import kotlin.time.Clock
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import osiris.fit.MainActivity
import osiris.fit.OsirisApplication
import osiris.fit.R

/**
 * Records the run: a foreground service with an ongoing notification that collects GPS fixes and adds
 * them to the shared RunRepository, which saves every point. Recording therefore does not depend on
 * the run screen: it goes on with the screen off, after leaving the screen, and when Android destroys
 * the activity. The service stops itself when the run is finished or discarded.
 *
 * It keeps no run state of its own, so a process that dies mid-run loses nothing but the fixes it
 * missed; the run screen recovers the saved run and starts the service again.
 */
class RunTrackingService : LifecycleService() {
    private var recording: Job? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        super.onStartCommand(intent, flags, startId)
        val type = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION else 0
        try {
            ServiceCompat.startForeground(this, NOTIFICATION_ID, notification(), type)
        } catch (e: RuntimeException) {
            // Android 12+ refuses a start from the background, and 14+ without location permission.
            // The run screen then records the fixes itself while it is open (see [recording]).
            stopSelf()
            return START_NOT_STICKY
        }
        // The run screen starts the service again whenever it opens on an active run: record once.
        if (recording == null) recording = record((application as OsirisApplication).graph.data.runs)
        return START_NOT_STICKY
    }

    private fun record(runs: RunRepository): Job = lifecycleScope.launch {
        _recording.value = true
        launch {
            // Finished or discarded, from any screen.
            runs.active.first { it == null }
            stopSelf()
        }
        // Not the cached position: it can be minutes old and would be saved as a point of this run.
        LocationClient(this@RunTrackingService).fixes(cached = false)
            .catch { e -> platformLogger().warn(TAG, "Location stopped while recording", e) }
            .collect { fix ->
                try {
                    runs.addFix(fix, Clock.System.now())
                } catch (e: AppError) {
                    // The phone could not save this point; the next one is tried again.
                    platformLogger().warn(TAG, "Could not save a fix: ${e.userMessage}", e)
                }
            }
        // The fixes only end on an error (location switched off, permission revoked). The run stays
        // open; the run screen says why and starts the service again when it next opens.
        stopSelf()
    }

    override fun onDestroy() {
        _recording.value = false
        super.onDestroy()
    }

    private fun notification(): Notification {
        val manager = getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            manager.createNotificationChannel(
                NotificationChannel(CHANNEL_ID, getString(R.string.run_channel_name), NotificationManager.IMPORTANCE_LOW),
            )
        }
        val open = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(getString(R.string.run_notification_title))
            .setContentText(getString(R.string.run_notification_text))
            .setSmallIcon(R.drawable.ic_stat_run)
            .setOngoing(true)
            .setContentIntent(open)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .build()
    }

    companion object {
        private const val TAG = "OsirisRun"
        private const val CHANNEL_ID = "run_recording"
        private const val NOTIFICATION_ID = 41

        private val _recording = MutableStateFlow(false)

        /**
         * True while the service is adding fixes to the run. Whoever else receives fixes (the run screen)
         * must not add them too, or every point would be saved twice.
         */
        val recording: StateFlow<Boolean> = _recording.asStateFlow()

        /** Starts recording the active run; the service stops by itself when the run ends. */
        fun start(context: Context) {
            runCatching { ContextCompat.startForegroundService(context, Intent(context, RunTrackingService::class.java)) }
        }
    }
}
