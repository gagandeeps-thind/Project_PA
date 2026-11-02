package com.osiris.player.ui.arise

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.FiberManualRecord
import androidx.compose.material.icons.outlined.Layers
import androidx.compose.material.icons.outlined.MyLocation
import androidx.compose.material.icons.outlined.PlayArrow
import androidx.compose.material3.BottomSheetScaffold
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.SmallFloatingActionButton
import androidx.compose.material3.Text
import androidx.compose.material3.rememberBottomSheetScaffoldState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.osiris.player.R
import com.osiris.player.ui.common.rememberShared
import com.osiris.player.ui.discover.DiscoverActions
import com.osiris.player.ui.discover.discoverSections
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.presentation.AppGraph

/** How much of the pull-up panel shows above the tab bar, about a centimetre. */
private val PEEK = 64.dp

/**
 * Arise: a full-screen map for runs, walks, hikes and trails. The rail on the right holds layers,
 * 2D/3D, locate-me, the + menu (start or record a route) and attack mode; the panel at the bottom
 * pulls up over the map.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AriseScreen(
    graph: AppGraph,
    onStartRoute: () -> Unit,
    onRecordRoute: () -> Unit,
    onOpenChallenge: (Int) -> Unit,
    onCreateChallenge: () -> Unit,
    onNearbyChallenges: () -> Unit,
) {
    val vm = rememberShared { graph.arise() }
    val discover = rememberShared { graph.discover() }
    val state by vm.state.collectAsStateWithLifecycle()
    val sections by discover.state.collectAsStateWithLifecycle()
    var recenter by remember { mutableIntStateOf(0) }
    var layersOpen by remember { mutableStateOf(false) }

    BottomSheetScaffold(
        scaffoldState = rememberBottomSheetScaffoldState(),
        sheetPeekHeight = PEEK,
        sheetDragHandle = {
            Box(Modifier.padding(vertical = 8.dp).size(36.dp, 4.dp).background(OsirisColors.Faint, RoundedCornerShape(2.dp)))
        },
        sheetContainerColor = OsirisColors.Surface,
        containerColor = Color.Transparent,
        sheetContent = {
            LazyColumn(Modifier.fillMaxWidth(), contentPadding = PaddingValues(bottom = 24.dp)) {
                item(key = "title") {
                    Text(
                        if (state.attackMode) "Domains to attack" else "Around you",
                        style = MaterialTheme.typography.titleLarge,
                        modifier = Modifier.padding(start = 16.dp, end = 16.dp, bottom = 8.dp),
                    )
                }
                if (state.attackMode) {
                    item(key = "attack-empty") {
                        Text("No domains near you yet.", color = OsirisColors.Faint, modifier = Modifier.padding(16.dp))
                    }
                } else {
                    item(key = "actions") { DiscoverActions(onCreateChallenge, onNearbyChallenges) }
                    discoverSections(sections, onOpenChallenge, onRetry = discover::load)
                }
            }
        },
    ) { padding ->
        Box(Modifier.fillMaxSize()) {
            AriseMap(state, recenter, Modifier.fillMaxSize())
            Column(
                Modifier.align(Alignment.BottomEnd).padding(end = 16.dp, bottom = padding.calculateBottomPadding() + 16.dp),
                horizontalAlignment = Alignment.End,
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                RailButton("Map layers", onClick = { layersOpen = true }) { Icon(Icons.Outlined.Layers, null) }
                RailButton(if (state.threeD) "Switch to 2D" else "Switch to 3D", onClick = vm::toggle3D) {
                    Text(if (state.threeD) "2D" else "3D", style = MaterialTheme.typography.labelLarge)
                }
                RailButton("Locate me", onClick = { recenter++ }) { Icon(Icons.Outlined.MyLocation, null) }
                AnimatedVisibility(state.fabOpen, enter = fadeIn() + expandVertically(), exit = fadeOut() + shrinkVertically()) {
                    Column(horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        MenuChoice("Start route", Icons.Outlined.PlayArrow) { vm.toggleFab(); onStartRoute() }
                        MenuChoice("Record route", Icons.Outlined.FiberManualRecord) { vm.toggleFab(); onRecordRoute() }
                    }
                }
                RailButton(if (state.fabOpen) "Close menu" else "Start or record a route", onClick = vm::toggleFab, accent = true) {
                    Icon(if (state.fabOpen) Icons.Outlined.Close else Icons.Outlined.Add, null)
                }
                RailButton(
                    if (state.attackMode) "Leave attack mode" else "Attack mode",
                    onClick = vm::toggleAttack,
                    accent = state.attackMode,
                ) { Icon(painterResource(R.drawable.ic_attack), null, Modifier.size(22.dp)) }
            }
            Text(
                "Arise",
                style = MaterialTheme.typography.headlineSmall,
                modifier = Modifier.align(Alignment.TopStart).statusBarsPadding().padding(16.dp),
            )
        }
    }
    if (layersOpen) LayersSheet(state, vm, onDismiss = { layersOpen = false })
}

@Composable
private fun RailButton(label: String, onClick: () -> Unit, accent: Boolean = false, content: @Composable () -> Unit) {
    SmallFloatingActionButton(
        onClick = onClick,
        containerColor = if (accent) OsirisColors.Primary else OsirisColors.Surface,
        contentColor = if (accent) Color.Black else MaterialTheme.colorScheme.onSurface,
        modifier = Modifier.semantics { contentDescription = label },
    ) { content() }
}

@Composable
private fun MenuChoice(label: String, icon: ImageVector, onClick: () -> Unit) {
    ExtendedFloatingActionButton(
        onClick = onClick,
        icon = { Icon(icon, null) },
        text = { Text(label) },
        containerColor = OsirisColors.Surface,
    )
}
