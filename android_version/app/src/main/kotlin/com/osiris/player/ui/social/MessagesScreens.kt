package com.osiris.player.ui.social

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.Send
import androidx.compose.material.icons.outlined.ChatBubbleOutline
import androidx.compose.material.icons.outlined.Edit
import androidx.compose.material3.Badge
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.LifecycleResumeEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.osiris.player.ui.common.EmptyState
import com.osiris.player.ui.common.LoadableContent
import com.osiris.player.ui.common.OsirisScaffold
import com.osiris.player.ui.common.rememberNow
import com.osiris.player.ui.common.rememberShared
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.domain.common.Format
import com.osiris.shared.domain.model.Conversation
import com.osiris.shared.domain.model.DirectMessage
import com.osiris.shared.presentation.AppGraph
import com.osiris.shared.presentation.common.Loadable
import com.osiris.shared.presentation.social.ChatState
import com.osiris.shared.presentation.social.InboxViewModel
import kotlin.time.Instant

/** Direct messages: conversations newest first, and a pencil to start one with a follower. */
@Composable
fun InboxScreen(graph: AppGraph, onBack: () -> Unit, onChat: (Int) -> Unit) {
    val vm = rememberShared { graph.inbox() }
    val s by vm.state.collectAsStateWithLifecycle()
    var picking by rememberSaveable { mutableStateOf(false) }
    var resumedOnce by rememberSaveable { mutableStateOf(false) }
    LifecycleResumeEffect(Unit) {
        if (resumedOnce) vm.refresh() else resumedOnce = true
        onPauseOrDispose {}
    }
    OsirisScaffold(
        "Messages",
        vm,
        onBack = onBack,
        actions = {
            IconButton(onClick = {
                picking = true
                vm.openNewMessage()
            }) { Icon(Icons.Outlined.Edit, contentDescription = "New message") }
        },
    ) { padding ->
        LoadableContent(s.inbox, onRetry = vm::refresh, modifier = Modifier.padding(padding)) { inbox ->
            if (inbox.items.isEmpty()) {
                Box(Modifier.fillMaxSize().padding(padding)) {
                    EmptyState(
                        Icons.Outlined.ChatBubbleOutline,
                        "No messages yet",
                        "Message your followers and the people you follow: plan a run, cheer a PR.",
                        actionLabel = "New message",
                        onAction = {
                            picking = true
                            vm.openNewMessage()
                        },
                    )
                }
            } else {
                val now = rememberNow()
                LazyColumn(Modifier.fillMaxSize().padding(padding)) {
                    items(inbox.items, key = { it.user.userId }) { c -> ConversationRow(c, now) { onChat(c.user.userId) } }
                }
            }
        }
    }
    if (picking) NewMessageSheet(vm, onDismiss = { picking = false }, onPick = {
        picking = false
        onChat(it)
    })
}

@Composable
private fun ConversationRow(c: Conversation, now: Instant, onClick: () -> Unit) {
    val unread = c.unreadCount > 0
    ListItem(
        leadingContent = { Avatar(c.user.initials, size = 48.dp) },
        headlineContent = { Text(c.user.displayName, fontWeight = if (unread) FontWeight.Bold else FontWeight.Normal) },
        supportingContent = {
            Text(
                (if (c.lastMessage.mine) "You: " else "") + c.lastMessage.body +
                    "  ·  " + Format.ago((now - c.lastMessage.createdAt).inWholeSeconds),
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                color = if (unread) MaterialTheme.colorScheme.onBackground else OsirisColors.Faint,
                fontWeight = if (unread) FontWeight.SemiBold else FontWeight.Normal,
            )
        },
        trailingContent = { if (unread) Badge { Text("${c.unreadCount}") } },
        colors = ListItemDefaults.colors(containerColor = Color.Transparent),
        modifier = Modifier.clickable(onClick = onClick),
    )
}

@Composable
private fun NewMessageSheet(vm: InboxViewModel, onDismiss: () -> Unit, onPick: (Int) -> Unit) {
    val s by vm.state.collectAsStateWithLifecycle()
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = OsirisColors.Surface,
    ) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 16.dp).navigationBarsPadding()) {
            Text("New message", style = MaterialTheme.typography.titleLarge)
            Text("Your followers and the people you follow", color = OsirisColors.Faint, fontSize = 12.sp)
            when (val contacts = s.contacts) {
                null, Loadable.Loading -> CircularProgressIndicator(Modifier.padding(24.dp))
                is Loadable.Failed -> Text(contacts.message, color = OsirisColors.Error, modifier = Modifier.padding(16.dp))
                is Loadable.Ready -> if (contacts.value.isEmpty()) {
                    Text("Follow someone first, or wait for a follower.", modifier = Modifier.padding(vertical = 24.dp))
                } else {
                    LazyColumn {
                        items(s.newMessageOptions, key = { it.userId }) { c ->
                            ListItem(
                                leadingContent = { Avatar(c.displayName.take(2).uppercase()) },
                                headlineContent = { Text(c.displayName) },
                                colors = ListItemDefaults.colors(containerColor = Color.Transparent),
                                modifier = Modifier.clickable { onPick(c.userId) },
                            )
                        }
                    }
                }
            }
        }
    }
}

/** One conversation, newest at the bottom, with a composer that follows the keyboard. */
@Composable
fun ChatScreen(graph: AppGraph, userId: Int, onBack: () -> Unit, onProfile: (Int) -> Unit) {
    val vm = rememberShared(key = "chat-$userId") { graph.chat(userId) }
    val s by vm.state.collectAsStateWithLifecycle()
    OsirisScaffold(
        s.user?.displayName ?: "Message",
        vm,
        onBack = onBack,
        actions = {
            s.user?.let { u ->
                Box(Modifier.padding(end = 8.dp)) { Avatar(u.initials, size = 32.dp, onClick = { onProfile(u.userId) }) }
            }
        },
    ) { padding ->
        Column(Modifier.fillMaxSize().padding(padding).imePadding()) {
            LoadableContent(s.messages, onRetry = vm::reload, modifier = Modifier.weight(1f)) { messages ->
                MessageList(messages, s, onOlder = vm::loadOlder, modifier = Modifier.weight(1f))
            }
            ChatComposer(s, onEdit = vm::edit, onSend = vm::send)
        }
    }
}

@Composable
private fun MessageList(messages: List<DirectMessage>, s: ChatState, onOlder: () -> Unit, modifier: Modifier) {
    val list = rememberLazyListState()
    // Newest at the bottom: jump there when a message arrives or is sent.
    LaunchedEffect(messages.lastOrNull()?.id) { if (messages.isNotEmpty()) list.animateScrollToItem(messages.lastIndex) }
    LazyColumn(
        state = list,
        modifier = modifier.fillMaxWidth(),
        contentPadding = PaddingValues(12.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        if (messages.isEmpty()) {
            item { Text("Say hi 👋  Plan your next session together.", color = OsirisColors.Faint, modifier = Modifier.padding(24.dp)) }
        } else if (!s.reachedStart) {
            item {
                Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                    TextButton(onClick = onOlder, enabled = !s.loadingOlder) { Text("Earlier messages") }
                }
            }
        }
        items(messages, key = { it.id }) { m -> Bubble(m) }
        if (messages.lastOrNull()?.let { it.mine && it.read } == true) {
            item { Text("Seen", fontSize = 11.sp, color = OsirisColors.Faint, modifier = Modifier.fillMaxWidth().padding(end = 4.dp)) }
        }
    }
}

@Composable
private fun Bubble(m: DirectMessage) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = if (m.mine) Arrangement.End else Arrangement.Start) {
        Text(
            m.body,
            color = if (m.mine) OsirisColors.OnPrimary else MaterialTheme.colorScheme.onBackground,
            modifier = Modifier
                .widthIn(max = 280.dp)
                .background(
                    if (m.mine) OsirisColors.Primary else OsirisColors.Surface,
                    RoundedCornerShape(
                        topStart = 18.dp,
                        topEnd = 18.dp,
                        bottomStart = if (m.mine) 18.dp else 4.dp,
                        bottomEnd = if (m.mine) 4.dp else 18.dp,
                    ),
                )
                .padding(horizontal = 14.dp, vertical = 9.dp),
        )
    }
}

@Composable
private fun ChatComposer(s: ChatState, onEdit: (String) -> Unit, onSend: () -> Unit) {
    if (s.user != null && !s.canMessage) {
        Text(
            "You can message people you follow or who follow you.",
            color = OsirisColors.Faint,
            modifier = Modifier.fillMaxWidth().padding(16.dp).navigationBarsPadding(),
        )
        return
    }
    Row(
        Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp).navigationBarsPadding(),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        OutlinedTextField(
            value = s.draft,
            onValueChange = onEdit,
            placeholder = { Text("Message…") },
            maxLines = 4,
            shape = RoundedCornerShape(24.dp),
            modifier = Modifier.weight(1f),
        )
        IconButton(
            onClick = onSend,
            enabled = s.canSend,
            modifier = Modifier.padding(start = 6.dp).size(48.dp).background(
                if (s.canSend) OsirisColors.Primary else OsirisColors.Surface,
                CircleShape,
            ),
        ) {
            if (s.sending) {
                CircularProgressIndicator(Modifier.size(20.dp))
            } else {
                Icon(
                    Icons.AutoMirrored.Outlined.Send,
                    contentDescription = "Send",
                    tint = if (s.canSend) OsirisColors.OnPrimary else MaterialTheme.colorScheme.onSurface,
                )
            }
        }
    }
}
