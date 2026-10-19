package com.osiris.player.platform.location

import android.Manifest
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalContext
import com.osiris.player.platform.permission.PermissionStatus
import com.osiris.player.platform.permission.rememberPermission
import com.osiris.shared.core.error.AppError
import com.osiris.shared.domain.run.LatLng
import kotlinx.coroutines.flow.first

/**
 * Asks for location if needed and reports one position, or why there is none. For screens that
 * only need to know roughly where the player is (nearby challenges).
 */
@Composable
fun CurrentPosition(onPosition: (LatLng) -> Unit, onUnavailable: (AppError) -> Unit) {
    val context = LocalContext.current
    val client = remember { LocationClient(context) }
    val permission = rememberPermission(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION)
    LaunchedEffect(permission) {
        when (permission) {
            PermissionStatus.UNKNOWN -> Unit
            PermissionStatus.REFUSED -> onUnavailable(LocationClient.permissionError())
            PermissionStatus.GRANTED -> try {
                onPosition(client.fixes().first().position)
            } catch (e: LocationUnavailable) {
                onUnavailable(e.error)
            }
        }
    }
}
