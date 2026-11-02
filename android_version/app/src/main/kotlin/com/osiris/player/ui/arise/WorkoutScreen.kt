package com.osiris.player.ui.arise

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.LifecycleResumeEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.osiris.player.ui.common.OsirisScaffold
import com.osiris.player.ui.common.rememberShared
import com.osiris.player.ui.design.FrostCard
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.presentation.AppGraph
import com.osiris.shared.presentation.arise.WorkoutTarget

/**
 * The Exceed or attack workout: each set opens the camera rep counter, then its rest runs, then the
 * player submits and the server checks every set against the verified camera sets.
 */
@Composable
fun WorkoutScreen(
    graph: AppGraph,
    target: WorkoutTarget,
    onCamera: (exerciseKey: String, reps: Int) -> Unit,
    onBack: () -> Unit,
) {
    val vm = rememberShared { graph.workout(target) }
    val s by vm.state.collectAsStateWithLifecycle()
    // The set whose camera screen is open; marked done when this screen comes back.
    var awaiting by rememberSaveable { mutableStateOf<Int?>(null) }
    LifecycleResumeEffect(awaiting) {
        awaiting?.let {
            vm.setDone(it)
            awaiting = null
        }
        onPauseOrDispose {}
    }
    LaunchedEffect(s.finished) { if (s.finished) onBack() }
    val title = if (target is WorkoutTarget.Exceed) "Exceed" else "Attack workout"
    OsirisScaffold(title, vm, onBack = onBack) { padding ->
        val workout = s.workout
        if (workout == null) {
            Text("Getting your workout…", color = OsirisColors.Muted, modifier = Modifier.padding(padding).padding(16.dp))
            return@OsirisScaffold
        }
        LazyColumn(
            Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item {
                Text(
                    "${workout.totalReps} reps in ${workout.sets.size} sets. Do them in order with the camera.",
                    color = OsirisColors.Muted,
                )
                s.restLeft?.let { left ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("Rest: $left s", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.weight(1f))
                        TextButton(onClick = vm::skipRest) { Text("Skip rest") }
                    }
                }
            }
            itemsIndexed(workout.sets) { index, set ->
                val done = index in s.done
                val next = !done && (0 until index).all { it in s.done } && s.restLeft == null
                FrostCard(Modifier.fillMaxWidth()) {
                    Text("${index + 1}. ${set.reps} × ${set.exerciseKey.replace('_', ' ')}", style = MaterialTheme.typography.titleMedium)
                    Text(if (done) "Done" else "Then rest ${set.restS} s", color = OsirisColors.Muted)
                    if (next) {
                        Button(onClick = {
                            awaiting = index
                            onCamera(set.exerciseKey, set.reps)
                        }, modifier = Modifier.fillMaxWidth().padding(top = 8.dp)) { Text("Start set") }
                    }
                }
            }
            item {
                OutlinedButton(onClick = vm::submit, enabled = s.allDone && !s.busy, modifier = Modifier.fillMaxWidth()) {
                    Text(if (target is WorkoutTarget.Exceed) "Defend my domain" else "Take the domain")
                }
            }
        }
    }
}
