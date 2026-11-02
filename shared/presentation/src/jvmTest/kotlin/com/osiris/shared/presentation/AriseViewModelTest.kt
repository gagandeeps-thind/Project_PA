package com.osiris.shared.presentation

import com.osiris.shared.domain.model.Heatmap
import com.osiris.shared.domain.model.MapStyle
import com.osiris.shared.domain.model.Overlay
import com.osiris.shared.domain.model.TerrainLayer
import com.osiris.shared.presentation.arise.AriseViewModel
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlinx.coroutines.test.UnconfinedTestDispatcher

class AriseViewModelTest {
    private fun vm() = AriseViewModel(dispatcher = UnconfinedTestDispatcher())

    @Test
    fun `the map opens on Standard with POIs and bike lanes, flat, no heatmap or terrain`() {
        val s = vm().state.value
        assertEquals(MapStyle.STANDARD, s.style)
        assertEquals(setOf(Overlay.POIS, Overlay.BIKE_LANES), s.overlays)
        assertFalse(s.threeD)
        assertNull(s.heatmap)
        assertNull(s.terrain)
    }

    @Test
    fun `heatmap and terrain are single choice and picking the same one again clears it`() {
        val vm = vm()
        vm.setHeatmap(Heatmap.GLOBAL)
        vm.setHeatmap(Heatmap.NIGHT)
        assertEquals(Heatmap.NIGHT, vm.state.value.heatmap)
        vm.setHeatmap(Heatmap.NIGHT)
        assertNull(vm.state.value.heatmap)
        vm.setTerrain(TerrainLayer.AVALANCHE)
        vm.setTerrain(TerrainLayer.ASPECT)
        assertEquals(TerrainLayer.ASPECT, vm.state.value.terrain)
        vm.setTerrain(TerrainLayer.ASPECT)
        assertNull(vm.state.value.terrain)
    }

    @Test
    fun `overlays toggle independently`() {
        val vm = vm()
        vm.toggleOverlay(Overlay.POIS)
        assertEquals(setOf(Overlay.BIKE_LANES), vm.state.value.overlays)
        vm.toggleOverlay(Overlay.POIS)
        assertTrue(Overlay.POIS in vm.state.value.overlays)
    }

    @Test
    fun `attack mode closes the plus menu and the plus menu leaves attack mode`() {
        val vm = vm()
        vm.toggleFab()
        vm.toggleAttack()
        assertTrue(vm.state.value.attackMode)
        assertFalse(vm.state.value.fabOpen)
        vm.toggleFab()
        assertTrue(vm.state.value.fabOpen)
        assertFalse(vm.state.value.attackMode)
    }

    @Test
    fun `style and 3D switch`() {
        val vm = vm()
        vm.setStyle(MapStyle.WINTER)
        vm.toggle3D()
        assertEquals(MapStyle.WINTER, vm.state.value.style)
        assertTrue(vm.state.value.threeD)
    }
}
