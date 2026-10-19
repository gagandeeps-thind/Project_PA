package com.osiris.player.ui.exercise

import android.Manifest
import android.content.Intent
import android.net.Uri
import android.provider.Settings
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.FiberManualRecord
import androidx.compose.material.icons.outlined.FiberManualRecord
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.LifecycleResumeEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.osiris.player.BuildConfig
import com.osiris.player.platform.permission.PermissionStatus
import com.osiris.player.platform.permission.granted
import com.osiris.player.platform.permission.rememberPermission
import com.osiris.player.platform.pose.PoseAnalyzer
import com.osiris.player.platform.pose.PoseCamera
import com.osiris.player.platform.pose.PoseImage
import com.osiris.player.ui.common.LoadableContent
import com.osiris.player.ui.common.OsirisScaffold
import com.osiris.player.ui.common.TextInputDialog
import com.osiris.player.ui.common.rememberShared
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.core.error.AppError
import com.osiris.shared.core.error.Outcome
import com.osiris.shared.domain.exercise.ExerciseCatalog
import com.osiris.shared.domain.exercise.ExerciseSpec
import com.osiris.shared.domain.exercise.Landmark
import com.osiris.shared.domain.exercise.PoseFrame
import com.osiris.shared.domain.exercise.Verdict
import com.osiris.shared.presentation.AppGraph
import com.osiris.shared.presentation.common.Loadable
import com.osiris.shared.presentation.exercise.ExerciseSessionState
import com.osiris.shared.presentation.exercise.ExerciseSessionViewModel
import com.osiris.shared.presentation.exercise.SetResult

@Composable
fun ExerciseCameraScreen(graph: AppGraph, key: String, onDone: () -> Unit) {
    // The catalog is cached by the repository (bundled copy offline), so this is immediate.
    val loaded by produceState<Loadable<Pair<ExerciseSpec, ExerciseCatalog>>>(Loadable.Loading, key) {
        value = when (val c = graph.data.exercises.catalog()) {
            is Outcome.Failure -> Loadable.failed(c.error)
            is Outcome.Success ->
                c.value.byKey(key)?.let { Loadable.Ready(it to c.value) } ?: Loadable.Failed("This exercise is not available.", canRetry = false)
        }
    }
    when (val l = loaded) {
        is Loadable.Ready -> Session(graph, l.value.first, l.value.second, onDone)
        else -> OsirisScaffold("Bodyweight", null, onBack = onDone) { padding ->
            LoadableContent(l, onRetry = {}, modifier = Modifier.padding(padding)) {}
        }
    }
}

@Composable
private fun Session(graph: AppGraph, spec: ExerciseSpec, catalog: ExerciseCatalog, onDone: () -> Unit) {
    val vm = rememberShared(key = "exercise-${spec.key}") { graph.exerciseSession(spec, catalog) }
    val s by vm.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    var frame by remember { mutableStateOf<PoseFrame?>(null) }
    var image by remember { mutableStateOf<PoseImage?>(null) }
    var analyzer by remember { mutableStateOf<PoseAnalyzer?>(null) }

    val permission = rememberPermission(Manifest.permission.CAMERA)
    var cameraAllowed by remember { mutableStateOf(context.granted(Manifest.permission.CAMERA)) }
    LaunchedEffect(permission) {
        when (permission) {
            PermissionStatus.GRANTED -> cameraAllowed = true
            PermissionStatus.REFUSED -> vm.onCameraFailed(AppError.Permission(Manifest.permission.CAMERA, "Camera access is off for Osiris. Allow it in Settings to count reps."))
            PermissionStatus.UNKNOWN -> Unit
        }
    }
    // Back from system Settings with the camera now allowed.
    LifecycleResumeEffect(Unit) {
        if (!cameraAllowed && context.granted(Manifest.permission.CAMERA)) cameraAllowed = true
        onPauseOrDispose {}
    }
    // Leaving mid-set finishes it, so the reps done so far are kept.
    BackHandler(enabled = s.phase == ExerciseSessionState.Phase.COUNTING) { vm.finish(perf(analyzer)) }

    OsirisScaffold(
        spec.name,
        vm,
        onBack = onDone,
        actions = {
            if (s.recordingAllowed) {
                IconButton(
                    onClick = { vm.setRecordLandmarks(!s.recordLandmarks) },
                    enabled = s.phase == ExerciseSessionState.Phase.READY,
                ) {
                    Icon(
                        if (s.recordLandmarks) Icons.Filled.FiberManualRecord else Icons.Outlined.FiberManualRecord,
                        if (s.recordLandmarks) "QA: stop recording landmarks" else "QA: record landmarks",
                        tint = if (s.recordLandmarks) OsirisColors.Error else OsirisColors.Faint,
                    )
                }
            }
        },
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding).background(Color.Black)) {
            if (cameraAllowed) {
                val img = image
                val box = if (img != null && img.height > 0) Modifier.aspectRatio(img.width.toFloat() / img.height) else Modifier.fillMaxSize()
                Box(box.align(Alignment.Center)) {
                    PoseCamera(
                        front = spec.camera == "front",
                        onStarted = {
                            analyzer = it
                            vm.onCameraStarted()
                        },
                        onFrame = { f, i ->
                            frame = f
                            if (i != image) image = i
                            vm.onFrame(f)
                        },
                        onFailed = vm::onCameraFailed,
                        modifier = Modifier.fillMaxSize(),
                    )
                    // Read in the draw phase only: a new frame redraws the overlay without recomposing the screen.
                    Skeleton({ frame }, image, catalog.minLikelihood)
                }
            }
            Column(Modifier.fillMaxWidth().padding(16.dp).align(Alignment.TopCenter)) {
                Hud(s)
                s.slowWarning?.let {
                    Text(
                        it,
                        color = Color.White,
                        fontSize = 13.sp,
                        modifier = Modifier.padding(top = 8.dp).fillMaxWidth()
                            .background(OsirisColors.Warning.copy(alpha = 0.85f), RoundedCornerShape(12.dp)).padding(10.dp),
                    )
                }
            }
            Column(Modifier.fillMaxWidth().padding(16.dp).navigationBarsPadding().align(Alignment.BottomCenter)) {
                val error = s.cameraError
                if (error != null) {
                    Text(error, color = OsirisColors.Error, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth())
                    Spacer(Modifier.height(12.dp))
                    Button(
                        onClick = {
                            context.startActivity(
                                Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.fromParts("package", context.packageName, null))
                                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                            )
                        },
                        modifier = Modifier.fillMaxWidth().height(52.dp),
                    ) { Text("OPEN SETTINGS") }
                } else {
                    val counting = s.phase == ExerciseSessionState.Phase.COUNTING
                    Button(
                        onClick = {
                            if (counting) {
                                vm.finish(perf(analyzer))
                            } else {
                                analyzer?.stats?.reset()
                                vm.start()
                            }
                        },
                        enabled = s.phase == ExerciseSessionState.Phase.READY || counting,
                        colors = ButtonDefaults.buttonColors(containerColor = if (counting) OsirisColors.Error else OsirisColors.Primary),
                        modifier = Modifier.fillMaxWidth().height(52.dp),
                    ) { Text(s.buttonLabel) }
                }
            }
        }
    }

    if (s.askLabel) {
        TextInputDialog(
            title = "QA: label this recording",
            body = null,
            label = s.labelPrompt,
            confirm = "SAVE",
            onConfirm = vm::labelRecording,
            dismiss = "DISCARD",
            onDismiss = { vm.labelRecording(null) },
            maxLength = 6,
            keyboard = KeyboardType.Decimal,
        )
    }
    s.result?.let { ResultSheet(it, onDone) }
}

/** Debug builds only: the pose timing read-out for the result sheet. */
private fun perf(analyzer: PoseAnalyzer?): String? = if (BuildConfig.DEBUG) analyzer?.stats?.summary() else null

@Composable
private fun Hud(s: ExerciseSessionState) {
    Row(
        Modifier.fillMaxWidth().background(Color.Black.copy(alpha = 0.54f), RoundedCornerShape(12.dp)).padding(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(s.hud.count, fontSize = 44.sp, fontWeight = FontWeight.Bold, color = Color.White)
        Spacer(Modifier.width(16.dp))
        Column(verticalArrangement = Arrangement.Center) {
            s.hud.notCounted?.let { Text(it, color = OsirisColors.Warning, fontSize = 12.sp) }
            Text(s.hud.hint, color = Color.White, fontSize = 15.sp)
        }
    }
}

private val bones = listOf("shoulder" to "elbow", "elbow" to "wrist", "shoulder" to "hip", "hip" to "knee", "knee" to "ankle")

/** Draws the tracked joints and limbs over the preview, so the player sees what is counted. */
@Composable
private fun Skeleton(frame: () -> PoseFrame?, image: PoseImage?, minLikelihood: Double) {
    Canvas(Modifier.fillMaxSize()) {
        val f = frame() ?: return@Canvas
        val img = image ?: return@Canvas
        if (img.width == 0 || img.height == 0) return@Canvas
        val sx = size.width / img.width
        val sy = size.height / img.height
        fun at(l: Landmark?): Offset? {
            if (l == null || l.likelihood < minLikelihood) return null
            val x = if (img.mirrored) img.width - l.x else l.x
            return Offset((x * sx).toFloat(), (l.y * sy).toFloat())
        }
        fun line(a: Offset?, b: Offset?) {
            if (a != null && b != null) drawLine(OsirisColors.Secondary, a, b, strokeWidth = 4.dp.toPx(), cap = StrokeCap.Round)
        }
        for (side in listOf("left", "right")) {
            for ((a, b) in bones) line(at(f.get(side, a)), at(f.get(side, b)))
        }
        line(at(f.get("left", "shoulder")), at(f.get("right", "shoulder")))
        line(at(f.get("left", "hip")), at(f.get("right", "hip")))
        for (l in f.landmarks.values) at(l)?.let { drawCircle(Color.White, radius = 5.dp.toPx(), center = it) }
    }
}

@Composable
private fun ResultSheet(r: SetResult, onDone: () -> Unit) {
    val color = when (r.verdict) {
        Verdict.VERIFIED -> OsirisColors.Success
        Verdict.REVIEW -> OsirisColors.Warning
        Verdict.REJECTED -> OsirisColors.Error
    }
    ModalBottomSheet(
        onDismissRequest = onDone,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = OsirisColors.Surface,
    ) {
        Column(Modifier.verticalScroll(rememberScrollState()).padding(24.dp).navigationBarsPadding()) {
            Text(r.title, color = color, fontSize = 22.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(8.dp))
            Text(r.amount, fontSize = 18.sp)
            r.notCounted?.let { Text(it) }
            Spacer(Modifier.height(8.dp))
            for (reason in r.reasons) Text("• $reason", color = OsirisColors.Muted)
            Spacer(Modifier.height(12.dp))
            Text(r.sync, color = OsirisColors.Secondary)
            r.perf?.let { Text("Pose: $it", color = OsirisColors.Faint, fontSize = 12.sp, modifier = Modifier.padding(top = 8.dp)) }
            Spacer(Modifier.height(16.dp))
            OutlinedButton(onClick = onDone, modifier = Modifier.fillMaxWidth()) { Text("DONE") }
        }
    }
}
