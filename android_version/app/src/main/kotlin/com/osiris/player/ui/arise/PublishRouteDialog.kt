package com.osiris.player.ui.arise

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.osiris.player.ui.theme.OsirisColors

private const val NAME_MIN = 3
private const val NAME_MAX = 60

/** After a recorded run: name the route and choose whether its start and finish stay hidden. */
@Composable
fun PublishRouteDialog(onPublish: (name: String, hideEnds: Boolean) -> Unit, onDismiss: () -> Unit) {
    var name by rememberSaveable { mutableStateOf("") }
    var hideEnds by rememberSaveable { mutableStateOf(true) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Publish this route?") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("Every Osiris player will see it on the Arise map and can run it.", color = OsirisColors.Muted)
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it.take(NAME_MAX) },
                    label = { Text("Route name") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Column(Modifier.weight(1f)) {
                        Text("Hide start and finish")
                        Text("Cuts about 150 m off each end, so your home or work stays private.", color = OsirisColors.Faint)
                    }
                    Switch(checked = hideEnds, onCheckedChange = { hideEnds = it })
                }
            }
        },
        confirmButton = {
            TextButton(onClick = { onPublish(name.trim(), hideEnds) }, enabled = name.trim().length >= NAME_MIN) { Text("Publish") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Not now") } },
    )
}
