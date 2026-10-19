package com.osiris.player.ui.permission

import android.Manifest
import android.content.Context
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.DirectionsWalk
import androidx.compose.material.icons.outlined.CameraAlt
import androidx.compose.material.icons.outlined.FavoriteBorder
import androidx.compose.material.icons.outlined.LocationOn
import androidx.compose.material.icons.outlined.Notifications
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.LifecycleResumeEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.osiris.player.platform.permission.granted
import com.osiris.player.ui.common.rememberShared
import com.osiris.player.ui.design.FrostBackground
import com.osiris.player.ui.design.FrostCard
import com.osiris.player.ui.theme.FrostTheme
import com.osiris.player.ui.theme.color
import com.osiris.player.ui.theme.primaryButtonColors
import com.osiris.shared.core.design.FrostMatte
import com.osiris.shared.domain.repository.DevicePermission
import com.osiris.shared.domain.repository.PermissionStatus
import com.osiris.shared.presentation.AppGraph
import com.osiris.shared.presentation.permission.PermissionItem

/**
 * The Android runtime permissions behind each primer entry. Health Connect is asked for through
 * its own contract once the health integration ships, so it is not offered here yet.
 */
private fun androidPermissions(p: DevicePermission): List<String> = when (p) {
    DevicePermission.LOCATION -> listOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION)
    DevicePermission.ACTIVITY ->
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) listOf(Manifest.permission.ACTIVITY_RECOGNITION) else emptyList()
    DevicePermission.CAMERA -> listOf(Manifest.permission.CAMERA)
    DevicePermission.NOTIFICATIONS ->
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) listOf(Manifest.permission.POST_NOTIFICATIONS) else emptyList()
    DevicePermission.HEALTH -> emptyList()
}

/** Entries that need a runtime prompt on this device; the rest are granted at install or not offered. */
private val promptable: Set<DevicePermission> = DevicePermission.entries.filter { androidPermissions(it).isNotEmpty() }.toSet()

private fun Context.grantedStatuses(): Map<DevicePermission, PermissionStatus> =
    promptable.filter { p -> androidPermissions(p).all(::granted) }.associateWith { PermissionStatus.GRANTED }

@Composable
fun PermissionPrimerScreen(graph: AppGraph) {
    val vm = rememberShared { graph.permissionPrimer(promptable) }
    val s by vm.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { result ->
        val asked = s.requesting ?: return@rememberLauncherForActivityResult
        val ok = androidPermissions(asked).all { result[it] == true || context.granted(it) }
        vm.onResult(asked, if (ok) PermissionStatus.GRANTED else PermissionStatus.DENIED)
    }
    LifecycleResumeEffect(Unit) {
        vm.onStatuses(context.grantedStatuses())
        onPauseOrDispose {}
    }
    LaunchedEffect(s.requesting) {
        s.requesting?.let { launcher.launch(androidPermissions(it).toTypedArray()) }
    }

    FrostBackground {
        Column(
            Modifier
                .fillMaxSize()
                .safeDrawingPadding()
                .verticalScroll(rememberScrollState())
                .padding(FrostMatte.Spacing.XL.dp),
            verticalArrangement = Arrangement.spacedBy(FrostMatte.Spacing.M.dp),
        ) {
            Text("Before you start", style = MaterialTheme.typography.headlineSmall, color = FrostTheme.palette.textPrimary.color())
            Text(
                "Osiris works without any of these. Allow what you want now; we ask again when you use the feature.",
                style = MaterialTheme.typography.bodyMedium,
                color = FrostTheme.palette.textSecondary.color(),
            )
            s.items.forEach { item -> PermissionCard(item, onAllow = { vm.request(item.permission) }) }
            FrostCard(Modifier.fillMaxWidth()) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("Share crash reports", style = MaterialTheme.typography.titleLarge)
                        Text(
                            "Anonymous diagnostics that help us fix crashes. Off unless you turn it on.",
                            style = MaterialTheme.typography.bodySmall,
                            color = FrostTheme.palette.textSecondary.color(),
                        )
                    }
                    Spacer(Modifier.width(FrostMatte.Spacing.M.dp))
                    Switch(checked = s.telemetry, onCheckedChange = vm::setTelemetry)
                }
            }
            Button(onClick = vm::finish, colors = primaryButtonColors(), modifier = Modifier.fillMaxWidth()) { Text("Continue") }
        }
    }
}

@Composable
private fun PermissionCard(item: PermissionItem, onAllow: () -> Unit) {
    val palette = FrostTheme.palette
    FrostCard(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(icon(item.permission), contentDescription = null, tint = palette.accent.color())
            Spacer(Modifier.width(FrostMatte.Spacing.M.dp))
            Column(Modifier.weight(1f)) {
                Text(item.title, style = MaterialTheme.typography.titleLarge)
                Text(item.purpose, style = MaterialTheme.typography.bodySmall, color = palette.textSecondary.color())
            }
            Spacer(Modifier.width(FrostMatte.Spacing.M.dp))
            when (item.status) {
                PermissionStatus.GRANTED -> Text("Allowed", color = palette.success.color(), style = MaterialTheme.typography.labelLarge)
                PermissionStatus.DENIED -> Text("Skipped", color = palette.textMuted.color(), style = MaterialTheme.typography.labelLarge)
                PermissionStatus.NOT_ASKED -> OutlinedButton(onClick = onAllow) { Text("Allow") }
            }
        }
    }
}

private fun icon(p: DevicePermission) = when (p) {
    DevicePermission.LOCATION -> Icons.Outlined.LocationOn
    DevicePermission.ACTIVITY -> Icons.AutoMirrored.Outlined.DirectionsWalk
    DevicePermission.HEALTH -> Icons.Outlined.FavoriteBorder
    DevicePermission.CAMERA -> Icons.Outlined.CameraAlt
    DevicePermission.NOTIFICATIONS -> Icons.Outlined.Notifications
}
