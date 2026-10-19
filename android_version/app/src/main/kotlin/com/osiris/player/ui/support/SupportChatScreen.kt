package com.osiris.player.ui.support

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.osiris.player.ui.common.OsirisScaffold
import com.osiris.player.ui.common.rememberShared
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.domain.model.SupportOutgoing
import com.osiris.shared.presentation.AppGraph
import com.osiris.shared.presentation.support.SupportChatState.Status

/** Live support chat. */
@Composable
fun SupportChatScreen(graph: AppGraph, onBack: () -> Unit) {
    val vm = rememberShared { graph.supportChat() }
    val s by vm.state.collectAsStateWithLifecycle()
    var draft by rememberSaveable { mutableStateOf("") }
    val list = rememberLazyListState()
    LaunchedEffect(s.lines.size) { if (s.lines.isNotEmpty()) list.animateScrollToItem(s.lines.lastIndex) }

    OsirisScaffold("SUPPORT", vm, onBack = onBack) { padding ->
        Column(Modifier.fillMaxSize().padding(padding).imePadding()) {
            LazyColumn(
                Modifier.weight(1f).fillMaxWidth(),
                state = list,
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                itemsIndexed(s.lines) { _, line ->
                    Box(Modifier.fillMaxWidth(), contentAlignment = if (line.mine) Alignment.CenterEnd else Alignment.CenterStart) {
                        Text(
                            line.text,
                            Modifier
                                .widthIn(max = 300.dp)
                                .background(
                                    if (line.mine) OsirisColors.Primary.copy(alpha = 0.32f) else OsirisColors.Faint.copy(alpha = 0.16f),
                                    RoundedCornerShape(12.dp),
                                )
                                .padding(12.dp),
                        )
                    }
                }
            }
            when (s.status) {
                Status.CONNECTING -> Text("Connecting…", color = OsirisColors.Faint, modifier = Modifier.padding(16.dp))
                Status.CLOSED -> Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(s.error ?: "Chat ended.", color = OsirisColors.Muted, modifier = Modifier.weight(1f))
                    OutlinedButton(onClick = vm::connect) { Text("RECONNECT") }
                }
                Status.OPEN -> Row(Modifier.padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
                    OutlinedTextField(
                        value = draft,
                        onValueChange = { if (it.length <= SupportOutgoing.MAX_LENGTH) draft = it },
                        placeholder = { Text("Message") },
                        modifier = Modifier.weight(1f),
                    )
                    IconButton(onClick = { if (vm.send(draft)) draft = "" }, enabled = draft.isNotBlank()) {
                        Icon(Icons.AutoMirrored.Filled.Send, "Send")
                    }
                }
            }
        }
    }
}
