package com.osiris.shared.presentation.arise

import com.osiris.shared.domain.model.AriseRoute
import com.osiris.shared.domain.model.Heatmap
import com.osiris.shared.domain.model.MapStyle
import com.osiris.shared.domain.model.Overlay
import com.osiris.shared.domain.model.TerrainLayer
import com.osiris.shared.domain.repository.AriseRepository
import com.osiris.shared.domain.run.Geo
import com.osiris.shared.domain.run.LatLng
import com.osiris.shared.domain.run.Sport
import com.osiris.shared.presentation.common.SharedViewModel
import kotlin.time.Duration.Companion.seconds
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** What the + menu was opened for. */
enum class RouteMode { START, RECORD }

/** The activity picker. Trail needs a forest or natural area nearby; null means the check has not answered. */
data class PickerState(val mode: RouteMode, val trailAllowed: Boolean? = null) {
    fun enabled(sport: Sport): Boolean = sport != Sport.TRAIL || trailAllowed != false
}

data class AriseState(
    val style: MapStyle = MapStyle.STANDARD,
    val overlays: Set<Overlay> = setOf(Overlay.POIS, Overlay.BIKE_LANES),
    val heatmap: Heatmap? = null,
    val terrain: TerrainLayer? = null,
    val threeD: Boolean = false,
    val fabOpen: Boolean = false,
    val attackMode: Boolean = false,
    val routes: List<AriseRoute> = emptyList(),
    val selectedRoute: AriseRoute? = null,
    val picker: PickerState? = null,
)

/** The Arise map: its look and layers, public routes around the player, the + menu and attack mode. */
class AriseViewModel(
    private val arise: AriseRepository,
    dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
) : SharedViewModel(dispatcher) {
    private val _state = MutableStateFlow(AriseState())
    val state: StateFlow<AriseState> = _state.asStateFlow()
    private var loadedAt: LatLng? = null

    fun setStyle(style: MapStyle) = _state.update { it.copy(style = style) }

    fun toggleOverlay(overlay: Overlay) = _state.update {
        it.copy(overlays = if (overlay in it.overlays) it.overlays - overlay else it.overlays + overlay)
    }

    fun setHeatmap(heatmap: Heatmap) = _state.update { it.copy(heatmap = heatmap.takeIf { h -> h != it.heatmap }) }

    fun setTerrain(layer: TerrainLayer) = _state.update { it.copy(terrain = layer.takeIf { l -> l != it.terrain }) }

    fun toggle3D() = _state.update { it.copy(threeD = !it.threeD) }

    fun toggleFab() = _state.update { it.copy(fabOpen = !it.fabOpen, attackMode = false) }

    fun toggleAttack() = _state.update { it.copy(attackMode = !it.attackMode, fabOpen = false) }

    fun openPicker(mode: RouteMode) = _state.update { it.copy(picker = PickerState(mode), fabOpen = false) }

    fun onTrailCheck(allowed: Boolean) = _state.update { s -> s.copy(picker = s.picker?.copy(trailAllowed = allowed)) }

    fun closePicker() = _state.update { it.copy(picker = null) }

    fun selectRoute(id: Int?) = _state.update { s -> s.copy(selectedRoute = s.routes.firstOrNull { it.id == id }) }

    /** Loads routes at the first position, then again once the player is [RELOAD_M] from where they last loaded. */
    fun onLocation(position: LatLng) {
        val last = loadedAt
        if (last != null && Geo.distanceM(last, position) < RELOAD_M) return
        loadedAt = position
        scope.launch {
            // The map is still useful without routes: a failure stays silent and is retried after a pause.
            val list = arise.nearbyRoutes(position).getOrNull()
            if (list != null) {
                _state.update { it.copy(routes = list) }
            } else {
                delay(RETRY_AFTER)
                loadedAt = null
            }
        }
    }

    private companion object {
        const val RELOAD_M = 1000.0
        val RETRY_AFTER = 30.seconds
    }
}
