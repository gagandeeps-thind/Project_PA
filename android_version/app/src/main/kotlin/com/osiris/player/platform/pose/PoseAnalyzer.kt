package com.osiris.player.platform.pose

import android.os.SystemClock
import androidx.annotation.OptIn
import androidx.camera.core.ExperimentalGetImage
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.pose.PoseDetection
import com.google.mlkit.vision.pose.PoseLandmark
import com.google.mlkit.vision.pose.defaults.PoseDetectorOptions
import com.osiris.shared.domain.exercise.Landmark
import com.osiris.shared.domain.exercise.PoseFrame
import java.util.concurrent.Executor

/** The upright image size pose coordinates refer to, and whether the preview is mirrored. */
data class PoseImage(val width: Int, val height: Int, val mirrored: Boolean)

/**
 * CameraX analyzer running ML Kit pose detection (the base model, stream mode) on the device.
 *
 * At most one frame is in flight: the [ImageProxy] is closed only when ML Kit returns, and the
 * analysis use case keeps only the latest frame, so a slow phone drops frames instead of queueing
 * them. Results are delivered on [callbackExecutor] (the main thread), one at a time.
 */
class PoseAnalyzer(
    private val mirrored: Boolean,
    private val callbackExecutor: Executor,
    private val onFrame: (PoseFrame, PoseImage) -> Unit,
) : ImageAnalysis.Analyzer {
    private val detector = PoseDetection.getClient(
        PoseDetectorOptions.Builder().setDetectorMode(PoseDetectorOptions.STREAM_MODE).build(),
    )
    val stats = PoseStats()

    // ExperimentalGetImage is an androidx (lint-checked) opt-in, hence androidx.annotation.OptIn.
    @OptIn(ExperimentalGetImage::class)
    override fun analyze(proxy: ImageProxy) {
        val media = proxy.image
        if (media == null) {
            proxy.close()
            return
        }
        val rotation = proxy.imageInfo.rotationDegrees
        val upright = if (rotation == 90 || rotation == 270) PoseImage(proxy.height, proxy.width, mirrored) else PoseImage(proxy.width, proxy.height, mirrored)
        // One monotonic clock for every camera session, so a reopened camera continues the timeline.
        val tMs = SystemClock.elapsedRealtime()
        val t0 = SystemClock.elapsedRealtimeNanos()
        detector.process(InputImage.fromMediaImage(media, rotation))
            .addOnSuccessListener(callbackExecutor) { pose ->
                stats.record(tMs, (SystemClock.elapsedRealtimeNanos() - t0) / 1_000)
                val landmarks = HashMap<String, Landmark>(NAMES.size)
                for ((type, name) in NAMES) {
                    pose.getPoseLandmark(type)?.let { l ->
                        landmarks[name] = Landmark(l.position.x.toDouble(), l.position.y.toDouble(), l.inFrameLikelihood.toDouble())
                    }
                }
                onFrame(PoseFrame(tMs, landmarks), upright)
            }
            .addOnFailureListener(callbackExecutor) { stats.fail() }
            .addOnCompleteListener { proxy.close() }
    }

    fun close() = detector.close()

    companion object {
        private val NAMES = listOf(
            PoseLandmark.NOSE to "nose",
            PoseLandmark.LEFT_SHOULDER to "left_shoulder",
            PoseLandmark.RIGHT_SHOULDER to "right_shoulder",
            PoseLandmark.LEFT_ELBOW to "left_elbow",
            PoseLandmark.RIGHT_ELBOW to "right_elbow",
            PoseLandmark.LEFT_WRIST to "left_wrist",
            PoseLandmark.RIGHT_WRIST to "right_wrist",
            PoseLandmark.LEFT_HIP to "left_hip",
            PoseLandmark.RIGHT_HIP to "right_hip",
            PoseLandmark.LEFT_KNEE to "left_knee",
            PoseLandmark.RIGHT_KNEE to "right_knee",
            PoseLandmark.LEFT_ANKLE to "left_ankle",
            PoseLandmark.RIGHT_ANKLE to "right_ankle",
        )
    }
}

/** Pose timing for the debug read-out on the result sheet: rate, mean and p95 latency. */
class PoseStats {
    private val latenciesUs = ArrayList<Long>()
    private var firstMs = 0L
    private var lastMs = 0L
    private var failed = 0

    @Synchronized
    fun record(tMs: Long, latencyUs: Long) {
        if (latenciesUs.isEmpty()) firstMs = tMs
        lastMs = tMs
        if (latenciesUs.size < MAX_SAMPLES) latenciesUs += latencyUs
    }

    @Synchronized
    fun fail() {
        failed++
    }

    @Synchronized
    fun summary(): String? {
        val n = latenciesUs.size
        if (n < 2) return null
        val sorted = latenciesUs.sorted()
        val meanMs = sorted.average() / 1000
        val p95Ms = sorted[((n - 1) * 0.95).toInt()] / 1000.0
        val fps = (n - 1) * 1000.0 / (lastMs - firstMs).coerceAtLeast(1)
        return String.format(java.util.Locale.ROOT, "%d frames, %.1f fps, %.0f ms mean, %.0f ms p95, %d failed", n, fps, meanMs, p95Ms, failed)
    }

    @Synchronized
    fun reset() {
        latenciesUs.clear()
        failed = 0
    }

    private companion object {
        const val MAX_SAMPLES = 30 * 60 * 10
    }
}
