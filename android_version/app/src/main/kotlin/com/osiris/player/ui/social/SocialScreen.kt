package com.osiris.player.ui.social

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.osiris.player.ui.common.OsirisScaffold
import com.osiris.player.ui.common.rememberShared
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.domain.model.BoardExercise
import com.osiris.shared.domain.model.BoardKind
import com.osiris.shared.domain.model.BoardPeriod
import com.osiris.shared.domain.model.BoardRow
import com.osiris.shared.domain.model.GlobalBoard
import com.osiris.shared.presentation.AppGraph
import com.osiris.shared.presentation.common.Loadable

/** Global boards, with ways into local rankings, seasons and communities. */
@Composable
fun SocialScreen(graph: AppGraph, onLocal: () -> Unit, onCommunities: () -> Unit) {
    val vm = rememberShared { graph.globalBoards() }
    val s by vm.state.collectAsStateWithLifecycle()
    OsirisScaffold("SOCIAL", vm) { padding ->
        PullToRefreshBox(isRefreshing = false, onRefresh = vm::refresh, modifier = Modifier.fillMaxSize().padding(padding)) {
            LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp)) {
                item {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(onClick = onLocal, modifier = Modifier.weight(1f)) { Text("LOCAL & SEASONS") }
                        OutlinedButton(onClick = onCommunities, modifier = Modifier.weight(1f)) { Text("COMMUNITIES") }
                    }
                }
                item { Chips(BoardKind.entries, s.kind, { it.title }) { vm.select(it) } }
                item { Chips(BoardPeriod.entries, s.period, { it.title }) { vm.select(it) } }
                if (s.showsExercise) item { Chips(BoardExercise.entries, s.exercise, { it.title }) { vm.select(it) } }
                when (val board = s.board) {
                    Loadable.Loading -> item { LinearProgressIndicator(Modifier.fillMaxWidth().padding(top = 16.dp)) }
                    is Loadable.Failed -> item { Text(board.message, color = OsirisColors.Error, modifier = Modifier.padding(top = 16.dp)) }
                    is Loadable.Ready -> board(board.value)
                }
            }
        }
    }
}

private fun LazyListScope.board(b: GlobalBoard) {
    item { Text(b.explainer, color = OsirisColors.Faint, fontSize = 12.sp, modifier = Modifier.padding(vertical = 12.dp)) }
    if (b.rows.isEmpty()) item { Text("Nobody is on this board yet. One verified session puts you on it.") }
    // No keys: tied ranks and "Private runner" names repeat, and the list is replaced, not edited.
    items(b.rows) { BoardRowItem(b, it) }
    val me = b.myRow
    if (me != null && b.rows.none { it.isMe }) {
        item { HorizontalDivider() }
        item { BoardRowItem(b, me) }
    }
    item {
        Text("${b.rankedPlayers} ranked players", color = OsirisColors.Faint, fontSize = 12.sp, modifier = Modifier.padding(top = 8.dp))
    }
}

@Composable
private fun BoardRowItem(b: GlobalBoard, r: BoardRow) {
    ListItem(
        leadingContent = { Text("#${r.rank}", fontWeight = FontWeight.Bold, modifier = Modifier.width(40.dp)) },
        headlineContent = {
            Text(if (r.isMe) "${r.name} (you)" else r.name, color = if (r.isMe) OsirisColors.Secondary else Color.Unspecified)
        },
        trailingContent = { Text(b.format(r.value)) },
        colors = ListItemDefaults.colors(containerColor = Color.Transparent),
    )
}

@Composable
private fun <T> Chips(options: List<T>, selected: T, label: (T) -> String, onSelect: (T) -> Unit) {
    Row(Modifier.horizontalScroll(rememberScrollState()).padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        for (o in options) FilterChip(selected = o == selected, onClick = { onSelect(o) }, label = { Text(label(o)) })
    }
}
