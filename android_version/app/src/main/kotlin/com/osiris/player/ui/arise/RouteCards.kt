package com.osiris.player.ui.arise

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.osiris.player.ui.design.FrostCard
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.domain.common.Format
import com.osiris.shared.domain.model.AriseRoute

/** The route the player tapped on the map, with its creator's time to beat. */
@Composable
fun RouteCard(route: AriseRoute, onStart: () -> Unit, onClose: () -> Unit) {
    FrostCard(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Dot(route.activityType)
            Text(route.name, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f).padding(start = 8.dp))
            IconButton(onClick = onClose) { Icon(Icons.Outlined.Close, "Close route") }
        }
        Text(
            "${route.activityType.replaceFirstChar { it.uppercase() }}  •  ${Format.km(route.distanceM)}  •  " +
                "best ${Format.duration(route.benchmarkSeconds)} by ${route.ownerName}",
            color = OsirisColors.Muted,
        )
        Button(onClick = onStart, modifier = Modifier.fillMaxWidth().padding(top = 8.dp)) { Text("Start this route") }
    }
}

/** What the line colours mean, and how many routes are around. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun RouteLegend(count: Int) {
    Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp)) {
        Text(if (count == 1) "1 route near you" else "$count routes near you", color = OsirisColors.Muted)
    }
    FlowRow(Modifier.padding(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(16.dp)) {
        ActivityColors.byActivity.keys.forEach { activity ->
            Row(verticalAlignment = Alignment.CenterVertically) {
                Dot(activity)
                Text(activity.replaceFirstChar { it.uppercase() }, modifier = Modifier.padding(start = 6.dp))
            }
        }
    }
}

@Composable
private fun Dot(activity: String) {
    Box(Modifier.size(12.dp).background(ActivityColors.of(activity), CircleShape))
}
