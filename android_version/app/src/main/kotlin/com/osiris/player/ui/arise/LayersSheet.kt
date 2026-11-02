package com.osiris.player.ui.arise

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.domain.model.Heatmap
import com.osiris.shared.domain.model.MapStyle
import com.osiris.shared.domain.model.Overlay
import com.osiris.shared.domain.model.TerrainLayer
import com.osiris.shared.presentation.arise.AriseState
import com.osiris.shared.presentation.arise.AriseViewModel

/** Map style, heatmaps, overlays and terrain. Heatmap and terrain are one-at-a-time; tapping the active one turns it off. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LayersSheet(state: AriseState, vm: AriseViewModel, onDismiss: () -> Unit) {
    ModalBottomSheet(onDismissRequest = onDismiss, containerColor = OsirisColors.Surface) {
        Column(Modifier.verticalScroll(rememberScrollState()).padding(start = 16.dp, end = 16.dp, bottom = 32.dp)) {
            Group("Map style", MapStyle.entries, { it == state.style }, { it.label }, vm::setStyle)
            Group("Heatmaps", Heatmap.entries, { it == state.heatmap }, { it.label }, vm::setHeatmap)
            Group("Layers", Overlay.entries, { it in state.overlays }, { it.label }, vm::toggleOverlay)
            Group("Terrain", TerrainLayer.entries, { it == state.terrain }, { it.label }, vm::setTerrain)
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun <T> Group(title: String, items: List<T>, selected: (T) -> Boolean, label: (T) -> String, onClick: (T) -> Unit) {
    Text(title, style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(top = 16.dp, bottom = 8.dp))
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        items.forEach { item -> FilterChip(selected = selected(item), onClick = { onClick(item) }, label = { Text(label(item)) }) }
    }
}
