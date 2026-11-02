package com.osiris.player.ui.arise

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.domain.common.Format
import com.osiris.shared.presentation.run.RunDialog
import kotlinx.coroutines.launch

/**
 * The player holds a domain (claimed or captured): Finish keeps it with the run alone, Exceed opens a
 * workout that attackers will have to repeat. A photo for the attack cards can be added here.
 */
@Composable
fun FinishOrExceedDialog(dialog: RunDialog.FinishOrExceed, onFinish: () -> Unit, onExceed: () -> Unit, onPhoto: (String) -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val pick = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        if (uri != null) scope.launch { photoForUpload(context, uri)?.let(onPhoto) }
    }
    val d = dialog.domain
    AlertDialog(
        onDismissRequest = onFinish,
        title = { Text(if (dialog.captured) "Domain captured!" else "Domain claimed!") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(
                    "Attackers must run at least ${Format.km(d.distanceM)} around it in under ${Format.duration(d.durationS)}.",
                    color = OsirisColors.Muted,
                )
                Text("Exceed: add a 30–100 rep camera workout they must repeat too.", color = OsirisColors.Faint)
                OutlinedButton(
                    onClick = { pick.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)) },
                    modifier = Modifier.fillMaxWidth(),
                ) { Text("Add a photo") }
            }
        },
        confirmButton = { Button(onClick = onExceed) { Text("Exceed") } },
        dismissButton = { TextButton(onClick = onFinish) { Text("Finish") } },
    )
}
