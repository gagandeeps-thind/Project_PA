package osiris.fit.platform.crash

import android.content.Context
import java.io.File
import java.time.Instant

/**
 * Keeps a short record of each crash in a private file (`files/crashes.log`), so a crash on a tester's
 * phone can be read back with `adb shell run-as osiris.fit cat files/crashes.log`. Nothing is uploaded
 * and no screen shows it; a crash reporting service (Crashlytics or Sentry) is a separate decision.
 *
 * The app still crashes as before: the record is written, then the system's handler runs.
 */
object CrashLog {
    private const val FILE = "crashes.log"
    private const val MAX_BYTES = 64 * 1024
    private const val MAX_FRAMES = 12
    private const val MAX_CAUSES = 3
    private const val MAX_MESSAGE = 300

    fun install(context: Context, version: String) {
        val file = File(context.applicationContext.filesDir, FILE)
        val system = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, error ->
            // Whatever goes wrong here (a full disk, no memory left), the crash itself must still be reported.
            runCatching { append(file, record(Instant.now().toString(), version, thread.name, error)) }
            system?.uncaughtException(thread, error)
        }
    }

    /** One crash as text: when, which build and thread, then the exception and its causes with their top frames. */
    internal fun record(at: String, version: String, thread: String, error: Throwable): String = buildString {
        append(at).append(" v").append(version).append(" thread=").append(thread).append('\n')
        var current: Throwable? = error
        var depth = 0
        while (current != null && depth <= MAX_CAUSES) {
            if (depth > 0) append("Caused by: ")
            append(current.javaClass.name)
            current.message?.let { append(": ").append(it.take(MAX_MESSAGE)) }
            append('\n')
            for (frame in current.stackTrace.take(MAX_FRAMES)) append("  at ").append(frame).append('\n')
            current = current.cause.takeIf { it !== current }
            depth++
        }
    }

    /** Appends [record], first dropping the older half once the file passes [MAX_BYTES]. */
    internal fun append(file: File, record: String) {
        if (file.length() > MAX_BYTES) file.writeText(file.readText().takeLast(MAX_BYTES / 2))
        file.appendText(record + "\n")
    }
}
