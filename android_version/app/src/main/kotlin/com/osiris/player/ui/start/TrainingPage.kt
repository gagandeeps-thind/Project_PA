package com.osiris.player.ui.start

import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.LifecycleResumeEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.osiris.player.ui.common.OsirisScaffold
import com.osiris.player.ui.common.SectionHeader
import com.osiris.player.ui.common.rememberShared
import com.osiris.player.ui.theme.OsirisColors
import androidx.compose.material3.Text
import com.osiris.shared.domain.model.StartMode
import com.osiris.shared.domain.model.TrainingActivity
import com.osiris.shared.presentation.AppGraph
import com.osiris.shared.presentation.common.Loadable
import kotlin.time.Instant

/** A camera set the coach handed back to this page: which activity, its id and when it began. */
data class CameraSet(val activityKey: String, val setId: String, val startedAt: Instant)

/**
 * Train or Challenge: the activity ribbon, the quote board and the start button, then Results and
 * charts (Train) or Osiris, group and suggested challenges (Challenge).
 */
@Composable
fun TrainingPage(
    graph: AppGraph,
    mode: StartMode,
    onBack: () -> Unit,
    onLive: (TrainingActivity) -> Unit,
    onCamera: (TrainingActivity) -> Unit,
    onChallenge: (Int) -> Unit,
    onGroups: () -> Unit,
    onGroup: (Int) -> Unit,
    cameraSet: CameraSet?,
    onCameraSetHandled: () -> Unit,
) {
    val vm = rememberShared(key = "start-${mode.wire}") { graph.start(mode) }
    val s by vm.state.collectAsStateWithLifecycle()
    var picking by rememberSaveable { mutableStateOf(false) }
    var expanded by rememberSaveable { mutableStateOf(false) }
    // Saveable: this screen leaves composition while another is open, and must still refresh on return.
    var resumed by rememberSaveable { mutableStateOf(false) }
    // Back from a session or a challenge, the numbers here may have moved.
    LifecycleResumeEffect(Unit) {
        if (resumed) vm.refresh() else resumed = true
        onPauseOrDispose { }
    }
    LaunchedEffect(cameraSet) {
        cameraSet?.let {
            vm.saveCameraSet(it.activityKey, it.setId, it.startedAt)
            onCameraSetHandled()
        }
    }
    OsirisScaffold(mode.title, vm, onBack = onBack) { padding ->
        LazyColumn(Modifier.fillMaxSize().padding(padding), contentPadding = PaddingValues(bottom = 24.dp)) {
            item { ActivityRibbon(s.activities, s.selected?.key, vm::select) }
            item { QuoteBoard(s.quote, Modifier.padding(16.dp)) }
            item { StartButton(s.selected) { picking = true } }
            when (mode) {
                StartMode.TRAIN -> {
                    item { SectionHeader("Results · ${s.selected?.name.orEmpty()}") }
                    item {
                        when (val summary = s.summary) {
                            is Loadable.Ready -> s.selected?.let { a ->
                                ResultsRow(summary.value, a)
                                SectionHeader("Last session")
                                TelemetryCharts(summary.value.latest, Modifier.padding(horizontal = 16.dp))
                            }
                            is Loadable.Failed -> Text(summary.message, color = OsirisColors.Error, modifier = Modifier.padding(16.dp))
                            else -> LinearProgressIndicator(Modifier.fillMaxWidth().padding(16.dp))
                        }
                    }
                }
                StartMode.CHALLENGE -> challengeSections(
                    s.groups, s.suggested, expanded,
                    onToggle = { expanded = !expanded },
                    onGroup = onGroup, onAllGroups = onGroups, onChallenge = onChallenge,
                )
            }
        }
    }
    if (picking) {
        ActivityPickerSheet(
            s.activities, s.selected,
            onStart = { a ->
                picking = false
                vm.select(a)
                if (vm.isCamera(a)) onCamera(a) else onLive(a)
            },
            onDismiss = { picking = false },
        )
    }
    s.pendingPost?.let { session ->
        val name = s.activities.firstOrNull { it.key == session.activityKey }?.name ?: "Workout"
        PostOrSaveDialog(session, name, onPost = vm::post, onKeep = vm::keep)
    }
}
