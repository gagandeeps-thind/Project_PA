package com.osiris.player.ui.start

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.domain.common.Format
import com.osiris.shared.domain.model.TrainingSession

private const val CAPTION_MAX = 600

/** After a session: post it to the feed, or just keep it in your history. It is saved either way. */
@Composable
fun PostOrSaveDialog(session: TrainingSession, activityName: String, onPost: (String) -> Unit, onKeep: () -> Unit) {
    var caption by rememberSaveable { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onKeep,
        containerColor = OsirisColors.Surface,
        title = { Text(if (session.isPr) "New personal record!" else "$activityName saved") },
        text = {
            Column {
                Text(summaryLine(session))
                Text(
                    "Saved to your Progress. Post it to People's Posts too?",
                    color = OsirisColors.Muted,
                    modifier = Modifier.padding(top = 8.dp, bottom = 8.dp),
                )
                OutlinedTextField(
                    value = caption,
                    onValueChange = { if (it.length <= CAPTION_MAX) caption = it },
                    label = { Text("Caption (optional)") },
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
        confirmButton = { Button(onClick = { onPost(caption.trim()) }) { Text("Post") } },
        dismissButton = { TextButton(onClick = onKeep) { Text("Just save") } },
    )
}

fun summaryLine(s: TrainingSession): String = buildList {
    add(Format.duration(s.durationS))
    if (s.distanceM > 0) add(Format.distance(s.distanceM))
    if (s.reps > 0) add("${s.reps} reps")
    s.hrAvg?.let { add("${it.toInt()} bpm avg") }
}.joinToString(" · ")
