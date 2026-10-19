package com.osiris.player.platform.share

import android.content.Context
import android.content.Intent
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.platform.LocalContext
import com.osiris.shared.presentation.common.ShareRequest

/** Opens the system share sheet for [request], then reports back so the share is tracked. */
@Composable
fun ShareEffect(request: ShareRequest?, onShared: (Boolean) -> Unit) {
    val context = LocalContext.current
    LaunchedEffect(request) {
        val r = request ?: return@LaunchedEffect
        onShared(share(context, r.text))
    }
}

/** True when a share target exists and the sheet opened; Android does not say whether the player sent it. */
fun share(context: Context, text: String): Boolean {
    val send = Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, text)
    val chooser = Intent.createChooser(send, null).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    return runCatching { context.startActivity(chooser) }.isSuccess
}
