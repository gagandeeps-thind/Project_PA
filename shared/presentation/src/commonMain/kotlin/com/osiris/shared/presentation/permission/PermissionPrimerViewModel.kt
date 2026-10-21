package com.osiris.shared.presentation.permission

import com.osiris.shared.domain.repository.DevicePermission
import com.osiris.shared.domain.repository.DeviceSetupRepository
import com.osiris.shared.domain.repository.PermissionStatus
import com.osiris.shared.presentation.common.SharedViewModel
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class PermissionItem(
    val permission: DevicePermission,
    val title: String,
    val purpose: String,
    val status: PermissionStatus,
)

/**
 * @property requesting the permission the platform should ask the OS for now; the screen calls
 *   [PermissionPrimerViewModel.onResult] with the answer
 */
data class PermissionPrimerState(
    val items: List<PermissionItem>,
    val telemetry: Boolean,
    val requesting: DevicePermission? = null,
)

/**
 * The pre-sign-in permission primer. Every permission states its purpose and can be skipped:
 * the app works without any of them and asks again where the feature is used (App Store 5.1.1,
 * Play prominent-disclosure rules). Telemetry is an opt-in choice, not an OS permission.
 */
class PermissionPrimerViewModel(
    private val setup: DeviceSetupRepository,
    available: Set<DevicePermission> = DevicePermission.entries.toSet(),
    dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
) : SharedViewModel(dispatcher) {
    private val _state = MutableStateFlow(
        PermissionPrimerState(
            items = DevicePermission.entries.filter { it in available }
                .map { PermissionItem(it, title(it), purpose(it), PermissionStatus.NOT_ASKED) },
            telemetry = setup.telemetryConsent.value,
        ),
    )
    val state: StateFlow<PermissionPrimerState> = _state.asStateFlow()

    /** The screen reports what the OS says on every resume, so a grant made in system settings shows. */
    fun onStatuses(statuses: Map<DevicePermission, PermissionStatus>) = _state.update { s ->
        s.copy(items = s.items.map { item -> statuses[item.permission]?.let { item.copy(status = it) } ?: item })
    }

    fun request(permission: DevicePermission) = _state.update { it.copy(requesting = permission) }

    fun onResult(permission: DevicePermission, status: PermissionStatus) = _state.update { s ->
        s.copy(
            requesting = null,
            items = s.items.map { if (it.permission == permission) it.copy(status = status) else it },
        )
    }

    fun setTelemetry(granted: Boolean) {
        _state.update { it.copy(telemetry = granted) }
        scope.launch { setup.setTelemetryConsent(granted) }
    }

    /** Finishes the primer whatever was granted. */
    fun finish() {
        scope.launch { setup.completePrimer() }
    }

    private companion object {
        fun title(p: DevicePermission) = when (p) {
            DevicePermission.LOCATION -> "Location"
            DevicePermission.ACTIVITY -> "Motion & steps"
            DevicePermission.HEALTH -> "Health data"
            DevicePermission.CAMERA -> "Camera"
            DevicePermission.NOTIFICATIONS -> "Notifications"
        }

        fun purpose(p: DevicePermission) = when (p) {
            DevicePermission.LOCATION -> "Verifies your runs and finds challenges near you. Used only while you record or browse nearby."
            DevicePermission.ACTIVITY -> "Counts steps with your phone's step sensor and spots shaken-phone or in-vehicle cheating."
            DevicePermission.HEALTH -> "Reads steps, distance and energy from your health app to cross-check your runs. Read only."
            DevicePermission.CAMERA -> "Counts push-ups, squats and other reps on your phone. Video never leaves the device."
            DevicePermission.NOTIFICATIONS -> "Tells you when a challenge starts, ends, or you win."
        }
    }
}
