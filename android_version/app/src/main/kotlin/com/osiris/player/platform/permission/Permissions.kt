package com.osiris.player.platform.permission

import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.LifecycleResumeEffect

/** Whether a set of runtime permissions is granted: unknown until asked, then granted or refused. */
enum class PermissionStatus { UNKNOWN, GRANTED, REFUSED }

fun Context.granted(permission: String) =
    ContextCompat.checkSelfPermission(this, permission) == PackageManager.PERMISSION_GRANTED

/**
 * Asks for [permissions] once, when the screen opens, and reports the result. [required] is the
 * one that decides the outcome; the others (such as notifications) are asked for in the same prompt.
 */
@Composable
fun rememberPermission(required: String, vararg optional: String): PermissionStatus {
    val context = LocalContext.current
    var status by remember { mutableStateOf(if (context.granted(required)) PermissionStatus.GRANTED else PermissionStatus.UNKNOWN) }
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { result ->
        status = if (result[required] == true || context.granted(required)) PermissionStatus.GRANTED else PermissionStatus.REFUSED
    }
    LaunchedEffect(Unit) {
        val missing = (listOf(required) + optional).filterNot(context::granted)
        if (missing.isNotEmpty()) launcher.launch(missing.toTypedArray())
    }
    // The player may grant it in system settings and come back.
    LifecycleResumeEffect(Unit) {
        if (status == PermissionStatus.REFUSED && context.granted(required)) status = PermissionStatus.GRANTED
        onPauseOrDispose { }
    }
    return status
}

/** This app's page in system settings, where a refused permission can be granted. */
fun Context.openAppSettings() {
    startActivity(
        Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.fromParts("package", packageName, null))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
    )
}
