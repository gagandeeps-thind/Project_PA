package com.osiris.player.ui.start

import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.Orientation
import androidx.compose.foundation.gestures.draggable
import androidx.compose.foundation.gestures.rememberDraggableState
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.osiris.player.ui.design.FrostCard
import com.osiris.player.ui.design.KeyButton
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.domain.common.Format
import com.osiris.shared.domain.model.ActivityKind
import com.osiris.shared.domain.model.Quote
import com.osiris.shared.domain.model.TrainingActivity
import com.osiris.shared.domain.model.TrainingSummary
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.sin

private const val RIBBON_DEGREES_PER_SECOND = 6f
private const val FULL_TURN = 360f
private const val NANOS = 1_000_000_000f
private const val CHIP_SLOT_DP = 140f
private const val MIN_FACING = 0.05f
private const val CHIP_SHRINK = 0.3f
private const val TO_RADIANS = PI.toFloat() / 180f

/** Accent per kind of activity, for the ribbon chips and the picker. */
fun ActivityKind.tint(): Color = when (this) {
    ActivityKind.CAMERA -> CameraBlue
    ActivityKind.GPS -> GpsEmber
    ActivityKind.SENSOR -> SensorGreen
}

private val CameraBlue = Color(0xFF29B6F6)
private val GpsEmber = Color(0xFFFF6A1A)
private val SensorGreen = Color(0xFF66BB6A)

/**
 * A thin ribbon of every activity, wrapped round a cylinder that turns slowly about its vertical
 * axis. Drag to spin it; tap a chip to pick that activity.
 */
@Composable
fun ActivityRibbon(activities: List<TrainingActivity>, selected: String?, onSelect: (TrainingActivity) -> Unit) {
    if (activities.isEmpty()) {
        Spacer(Modifier.height(44.dp))
        return
    }
    var rotation by remember { mutableFloatStateOf(0f) }
    var dragging by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) {
        var last = 0L
        while (true) {
            withFrameNanos { now ->
                if (last != 0L && !dragging) rotation += RIBBON_DEGREES_PER_SECOND * (now - last) / NANOS
                last = now
            }
        }
    }
    val step = FULL_TURN / activities.size
    var degreesPerPx by remember { mutableFloatStateOf(0f) }
    // On the parent, so a drag that starts on a chip still spins the ribbon.
    val drag = rememberDraggableState { delta -> rotation -= delta * degreesPerPx }
    BoxWithConstraints(
        Modifier.fillMaxWidth().height(44.dp).clipToBounds().draggable(
            drag, Orientation.Horizontal,
            onDragStarted = { dragging = true },
            onDragStopped = { dragging = false },
        ),
        contentAlignment = Alignment.Center,
    ) {
        val density = LocalDensity.current
        // Big enough that the chips sit a slot apart round the circumference.
        val radiusPx = with(density) { max(activities.size * CHIP_SLOT_DP.dp.toPx() / (2 * PI.toFloat()), maxWidth.toPx() / 2) }
        SideEffect { degreesPerPx = FULL_TURN / (2 * PI.toFloat() * radiusPx) }
        activities.forEachIndexed { i, activity ->
            val angle = ((i * step - rotation) % FULL_TURN + FULL_TURN) % FULL_TURN
            val facing = cos(angle * TO_RADIANS)
            if (facing > MIN_FACING) {
                RibbonChip(
                    activity, activity.key == selected,
                    Modifier.graphicsLayer {
                        translationX = sin(angle * TO_RADIANS) * radiusPx
                        rotationY = -angle
                        alpha = facing
                        val scale = 1f - CHIP_SHRINK * (1f - facing)
                        scaleX = scale
                        scaleY = scale
                        cameraDistance = 12f * density.density
                    },
                ) { onSelect(activity) }
            }
        }
    }
}

@Composable
private fun RibbonChip(activity: TrainingActivity, selected: Boolean, modifier: Modifier, onClick: () -> Unit) {
    val tint = activity.kind.tint()
    val shape = RoundedCornerShape(50)
    Text(
        activity.name,
        style = MaterialTheme.typography.labelLarge,
        color = if (selected) Color.White else MaterialTheme.colorScheme.onBackground,
        maxLines = 1,
        overflow = TextOverflow.Ellipsis,
        textAlign = TextAlign.Center,
        modifier = modifier
            .width(128.dp)
            .clip(shape)
            .background(if (selected) tint else tint.copy(alpha = 0.16f))
            .border(1.dp, tint.copy(alpha = 0.6f), shape)
            .clickable(role = Role.Button, onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 8.dp),
    )
}

/** The motivation board: a new quote each time the app opens. */
@Composable
fun QuoteBoard(quote: Quote?, modifier: Modifier = Modifier) {
    FrostCard(modifier.fillMaxWidth()) {
        if (quote == null) {
            Text("Every session counts.", style = MaterialTheme.typography.titleMedium, fontStyle = FontStyle.Italic)
        } else {
            Text("“${quote.text}”", style = MaterialTheme.typography.titleMedium, fontStyle = FontStyle.Italic)
            Text("— ${quote.author}", color = OsirisColors.Muted, modifier = Modifier.padding(top = 6.dp))
        }
    }
}

/** The small round start key in the middle of the page. */
@Composable
fun StartButton(activity: TrainingActivity?, onClick: () -> Unit) {
    Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally) {
        Box(
            Modifier
                .size(96.dp)
                .clip(CircleShape)
                .background(Brush.verticalGradient(listOf(Color(0xFFFF8A3D), OsirisColors.Primary)))
                .clickable(role = Role.Button, onClick = onClick)
                .semantics { contentDescription = "Start ${activity?.name ?: "a workout"}" },
            contentAlignment = Alignment.Center,
        ) {
            Icon(StartIcon, contentDescription = null, tint = Color.White, modifier = Modifier.size(44.dp))
        }
        Text(
            "Start",
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(top = 8.dp),
        )
        activity?.let { Text(it.name, color = OsirisColors.Muted) }
    }
}

/** Choose what to start; the ribbon's choice is preselected. */
@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun ActivityPickerSheet(
    activities: List<TrainingActivity>,
    initial: TrainingActivity?,
    onStart: (TrainingActivity) -> Unit,
    onDismiss: () -> Unit,
) {
    var chosen by remember { mutableStateOf(initial ?: activities.firstOrNull()) }
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = OsirisColors.Surface,
    ) {
        Column(Modifier.padding(horizontal = 20.dp).navigationBarsPadding()) {
            Text("Select a workout", style = MaterialTheme.typography.titleLarge)
            for (kind in ActivityKind.entries) {
                val group = activities.filter { it.kind == kind }
                if (group.isEmpty()) continue
                Text(
                    when (kind) {
                        ActivityKind.GPS -> "Outdoors (GPS)"
                        ActivityKind.SENSOR -> "Watch & sensors"
                        ActivityKind.CAMERA -> "Camera coach"
                    },
                    color = OsirisColors.Muted,
                    modifier = Modifier.padding(top = 14.dp, bottom = 4.dp),
                )
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    for (a in group) {
                        FilterChip(selected = chosen?.key == a.key, onClick = { chosen = a }, label = { Text(a.name) })
                    }
                }
            }
            KeyButton(
                onClick = { chosen?.let(onStart) },
                enabled = chosen != null,
                modifier = Modifier.fillMaxWidth().padding(vertical = 20.dp),
            ) { Text("Start ${chosen?.name.orEmpty()}") }
        }
    }
}

/** Results for the chosen activity: five tiles at most. */
@Composable
fun ResultsRow(summary: TrainingSummary, activity: TrainingActivity) {
    val camera = activity.kind == ActivityKind.CAMERA
    val tiles = listOf(
        "PR" to (summary.pr?.let { prLabel(it.value, it.unit) } ?: "—"),
        "Segments" to "${summary.segments.workouts} · ${summary.segments.challenges}",
        "Total time" to Format.duration(summary.totalDurationS),
        if (camera) "Total reps" to "${summary.totalReps}" else "Distance" to Format.distance(summary.totalDistanceM),
        "This week" to "${summary.weekSessions}",
    )
    val captions = mapOf("Segments" to "workouts · challenges", "This week" to "sessions")
    Row(
        Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = 16.dp),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        for ((label, value) in tiles) {
            FrostCard(Modifier.width(136.dp).height(116.dp)) {
                Text(label, style = MaterialTheme.typography.labelMedium, color = OsirisColors.Muted)
                Text(value, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                captions[label]?.let { Text(it, style = MaterialTheme.typography.labelSmall, color = OsirisColors.Faint) }
            }
        }
    }
}

fun prLabel(value: Double, unit: String): String = when (unit) {
    "m" -> Format.distance(value)
    "s" -> Format.duration(value)
    else -> "${value.toInt()} $unit"
}
