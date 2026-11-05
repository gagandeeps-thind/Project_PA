package com.osiris.player.ui.social

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.PersonSearch
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.osiris.player.ui.common.EmptyState
import com.osiris.player.ui.common.OsirisScaffold
import com.osiris.player.ui.common.rememberShared
import com.osiris.player.ui.design.KeyButton
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.domain.model.SocialUser
import com.osiris.shared.presentation.AppGraph
import com.osiris.shared.presentation.common.Loadable

/** Find people by name or @handle, and follow them from the list. */
@Composable
fun SocialSearchScreen(graph: AppGraph, onBack: () -> Unit, onProfile: (Int) -> Unit) {
    val vm = rememberShared { graph.socialSearch() }
    val s by vm.state.collectAsStateWithLifecycle()
    val focus = remember { FocusRequester() }
    LaunchedEffect(Unit) { runCatching { focus.requestFocus() } }
    OsirisScaffold("Search", vm, onBack = onBack) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            OutlinedTextField(
                value = s.query,
                onValueChange = vm::query,
                leadingIcon = { Icon(Icons.Outlined.Search, null) },
                placeholder = { Text("Search by name or @handle") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp).focusRequester(focus),
            )
            when (val results = s.results) {
                null -> EmptyState(Icons.Outlined.PersonSearch, "Find training partners", "Type at least 2 letters of a name or handle.")
                Loadable.Loading -> LinearProgressIndicator(Modifier.fillMaxWidth().padding(horizontal = 16.dp))
                is Loadable.Failed -> Text(results.message, color = OsirisColors.Error, modifier = Modifier.padding(16.dp))
                is Loadable.Ready -> if (results.value.isEmpty()) {
                    EmptyState(Icons.Outlined.PersonSearch, "No one matches \"${s.query.trim()}\"")
                } else {
                    LazyColumn(contentPadding = PaddingValues(vertical = 4.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        items(results.value, key = { it.userId }) { u ->
                            PersonRow(u, onOpen = { onProfile(u.userId) }, onFollow = { vm.toggleFollow(u.userId) })
                        }
                    }
                }
            }
        }
    }
}

/** One person: avatar, name, @handle and rank, with a follow button. */
@Composable
fun PersonRow(u: SocialUser, onOpen: () -> Unit, onFollow: (() -> Unit)?) {
    ListItem(
        leadingContent = { Avatar(u.initials, onClick = onOpen) },
        headlineContent = { Text(u.displayName, fontWeight = FontWeight.SemiBold) },
        supportingContent = {
            Text(
                "@${u.handle} · ${u.rank}" + if (u.followsMe) " · Follows you" else "",
                color = OsirisColors.Faint,
            )
        },
        trailingContent = {
            if (onFollow != null) {
                if (u.following) {
                    OutlinedButton(onClick = onFollow) { Text("Following") }
                } else {
                    KeyButton(onClick = onFollow) { Text(if (u.followsMe) "Follow back" else "Follow") }
                }
            }
        },
        colors = ListItemDefaults.colors(containerColor = Color.Transparent),
        // The whole row opens the profile, as on Instagram; the follow button keeps its own tap.
        modifier = Modifier.clickable(onClick = onOpen).padding(horizontal = 4.dp),
    )
}
