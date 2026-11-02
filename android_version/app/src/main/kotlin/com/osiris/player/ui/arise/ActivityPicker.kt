package com.osiris.player.ui.arise

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.domain.run.Sport
import com.osiris.shared.presentation.arise.PickerState
import com.osiris.shared.presentation.arise.RouteMode

/** Run, walk, hike or trail. Trail is greyed out away from forest. */
@Composable
fun ActivityPicker(picker: PickerState, onPick: (Sport) -> Unit, onDismiss: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(if (picker.mode == RouteMode.RECORD) "Record a route" else "Start a route") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                for (sport in Sport.entries) {
                    OutlinedButton(onClick = { onPick(sport) }, enabled = picker.enabled(sport), modifier = Modifier.fillMaxWidth()) {
                        Text(sport.label)
                    }
                }
                when (picker.trailAllowed) {
                    false -> Text("Trail needs a forest or natural area nearby.", color = OsirisColors.Faint)
                    null -> Text("Checking the terrain around you…", color = OsirisColors.Faint)
                    true -> Unit
                }
            }
        },
        confirmButton = {},
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}
