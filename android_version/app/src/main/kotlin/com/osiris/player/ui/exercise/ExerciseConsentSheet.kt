package com.osiris.player.ui.exercise

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.CloudUpload
import androidx.compose.material.icons.outlined.PhoneAndroid
import androidx.compose.material.icons.outlined.ToggleOff
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.osiris.player.ui.theme.OsirisColors
import androidx.compose.material3.AlertDialog

private val points = listOf(
    Icons.Outlined.PhoneAndroid to "Camera images are analysed on this phone only, to find where your joints are. They are never saved or uploaded.",
    Icons.Outlined.CloudUpload to "Osiris keeps the exercise, your rep count, rep timings and a form score, to verify sets and award XP. This is health information.",
    Icons.Outlined.ToggleOff to "You can withdraw at any time in Settings, and delete your exercise history.",
)

/** Asks for camera exercise counting consent: what is analysed, what is kept, how to withdraw. */
@Composable
fun ExerciseConsentSheet(onAnswer: (Boolean) -> Unit) {
    ModalBottomSheet(
        onDismissRequest = { onAnswer(false) },
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = OsirisColors.Surface,
    ) {
        Column(Modifier.verticalScroll(rememberScrollState()).padding(24.dp).navigationBarsPadding()) {
            Text("Count reps with your camera?", style = MaterialTheme.typography.titleLarge)
            Spacer(Modifier.padding(top = 16.dp))
            for ((icon, text) in points) {
                Row(Modifier.padding(bottom = 12.dp), verticalAlignment = Alignment.Top) {
                    Icon(icon, null, tint = OsirisColors.Secondary)
                    Spacer(Modifier.width(12.dp))
                    Text(text)
                }
            }
            Button(onClick = { onAnswer(true) }, modifier = Modifier.fillMaxWidth().padding(top = 8.dp)) { Text("ALLOW") }
            TextButton(onClick = { onAnswer(false) }, modifier = Modifier.fillMaxWidth()) { Text("NOT NOW") }
        }
    }
}

/** Withdrawing consent: keep the sets already counted, or delete them here and on the server. */
@Composable
fun WithdrawExerciseConsentDialog(onKeep: () -> Unit, onDelete: () -> Unit, onCancel: () -> Unit) {
    AlertDialog(
        onDismissRequest = onCancel,
        containerColor = OsirisColors.Surface,
        title = { Text("Stop counting exercises?") },
        text = {
            Text(
                "Osiris will stop uploading exercise sets. You can also delete your exercise history " +
                    "from Osiris and this phone. XP you already earned stays.",
            )
        },
        confirmButton = {
            Row {
                TextButton(onClick = onCancel) { Text("CANCEL") }
                TextButton(onClick = onKeep) { Text("KEEP MY SETS") }
                TextButton(onClick = onDelete) { Text("DELETE MY SETS", color = OsirisColors.Error) }
            }
        },
    )
}
