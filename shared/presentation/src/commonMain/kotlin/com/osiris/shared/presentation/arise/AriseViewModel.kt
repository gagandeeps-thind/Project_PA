package com.osiris.shared.presentation.arise

import com.osiris.shared.domain.model.Heatmap
import com.osiris.shared.domain.model.MapStyle
import com.osiris.shared.domain.model.Overlay
import com.osiris.shared.domain.model.TerrainLayer
import com.osiris.shared.presentation.common.SharedViewModel
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update

data class AriseState(
    val style: MapStyle = MapStyle.STANDARD,
    val overlays: Set<Overlay> = setOf(Overlay.POIS, Overlay.BIKE_LANES),
    val heatmap: Heatmap? = null,
    val terrain: TerrainLayer? = null,
    val threeD: Boolean = false,
    val fabOpen: Boolean = false,
    val attackMode: Boolean = false,
)

/** The Arise map: its look, its layers, and which of the + menu and attack mode is open. */
class AriseViewModel(dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate) : SharedViewModel(dispatcher) {
    private val _state = MutableStateFlow(AriseState())
    val state: StateFlow<AriseState> = _state.asStateFlow()

    fun setStyle(style: MapStyle) = _state.update { it.copy(style = style) }

    fun toggleOverlay(overlay: Overlay) = _state.update {
        it.copy(overlays = if (overlay in it.overlays) it.overlays - overlay else it.overlays + overlay)
    }

    fun setHeatmap(heatmap: Heatmap) = _state.update { it.copy(heatmap = heatmap.takeIf { h -> h != it.heatmap }) }

    fun setTerrain(layer: TerrainLayer) = _state.update { it.copy(terrain = layer.takeIf { l -> l != it.terrain }) }

    fun toggle3D() = _state.update { it.copy(threeD = !it.threeD) }

    fun toggleFab() = _state.update { it.copy(fabOpen = !it.fabOpen, attackMode = false) }

    fun toggleAttack() = _state.update { it.copy(attackMode = !it.attackMode, fabOpen = false) }
}
