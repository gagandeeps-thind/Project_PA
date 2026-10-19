package com.osiris.player.platform.pose

import android.util.Size
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.core.resolutionselector.AspectRatioStrategy
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.osiris.shared.core.error.AppError
import com.osiris.shared.domain.exercise.PoseFrame
import java.util.concurrent.Executors

/**
 * Camera preview with pose analysis bound to the screen's lifecycle: CameraX stops the camera
 * when the app goes to the background and restarts it on return.
 *
 * The analysis stream is about 640x480 in 4:3 (pose landmarks need nothing larger), and the
 * preview uses the same aspect ratio with FIT_CENTER, so landmark coordinates scale straight onto
 * the preview for the skeleton overlay.
 */
@Composable
fun PoseCamera(
    front: Boolean,
    onStarted: (PoseAnalyzer) -> Unit,
    onFrame: (PoseFrame, PoseImage) -> Unit,
    onFailed: (AppError) -> Unit,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val owner = LocalLifecycleOwner.current
    val preview = remember { PreviewView(context).apply { scaleType = PreviewView.ScaleType.FIT_CENTER } }
    val worker = remember { Executors.newSingleThreadExecutor() }
    // The camera binds once; the callbacks it holds always reach the latest lambdas.
    val frame by rememberUpdatedState(onFrame)
    val started by rememberUpdatedState(onStarted)
    val failed by rememberUpdatedState(onFailed)

    DisposableEffect(owner, front) {
        val future = ProcessCameraProvider.getInstance(context)
        var analyzer: PoseAnalyzer? = null
        var provider: ProcessCameraProvider? = null
        future.addListener({
            try {
                val p = future.get().also { provider = it }
                val selector = when {
                    front && p.hasCamera(CameraSelector.DEFAULT_FRONT_CAMERA) -> CameraSelector.DEFAULT_FRONT_CAMERA
                    p.hasCamera(CameraSelector.DEFAULT_BACK_CAMERA) -> CameraSelector.DEFAULT_BACK_CAMERA
                    p.hasCamera(CameraSelector.DEFAULT_FRONT_CAMERA) -> CameraSelector.DEFAULT_FRONT_CAMERA
                    else -> {
                        failed(AppError.Validation("This phone has no camera."))
                        return@addListener
                    }
                }
                val mirrored = selector == CameraSelector.DEFAULT_FRONT_CAMERA
                val ratio = ResolutionSelector.Builder().setAspectRatioStrategy(AspectRatioStrategy.RATIO_4_3_FALLBACK_AUTO_STRATEGY)
                val previewCase = Preview.Builder().setResolutionSelector(ratio.build()).build()
                    .also { it.setSurfaceProvider(preview.surfaceProvider) }
                val a = PoseAnalyzer(mirrored, ContextCompat.getMainExecutor(context)) { f, image -> frame(f, image) }.also { analyzer = it }
                val analysis = ImageAnalysis.Builder()
                    .setResolutionSelector(
                        ratio.setResolutionStrategy(
                            ResolutionStrategy(Size(640, 480), ResolutionStrategy.FALLBACK_RULE_CLOSEST_HIGHER_THEN_LOWER),
                        ).build(),
                    )
                    .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                    .build()
                    .also { it.setAnalyzer(worker, a) }
                p.unbindAll()
                p.bindToLifecycle(owner, selector, previewCase, analysis)
                started(a)
            } catch (e: Exception) {
                failed(AppError.Unexpected(e))
            }
        }, ContextCompat.getMainExecutor(context))
        onDispose {
            provider?.unbindAll()
            analyzer?.close()
        }
    }
    DisposableEffect(Unit) { onDispose { worker.shutdown() } }

    AndroidView(factory = { preview }, modifier = modifier)
}
