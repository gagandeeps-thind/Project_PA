package com.osiris.player.ui.social

import android.widget.Toast
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.MoreVert
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.osiris.player.ui.common.ConfirmDialog
import com.osiris.player.ui.common.rememberShared
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.domain.model.ContentReportReason
import com.osiris.shared.domain.model.FeedPost
import com.osiris.shared.domain.model.PostCommentItem
import com.osiris.shared.domain.model.ReportKind
import com.osiris.shared.domain.repository.AuthState
import com.osiris.shared.presentation.AppGraph
import com.osiris.shared.presentation.social.ContentSafetyViewModel
import com.osiris.shared.presentation.social.SafetyPrompt

/** Report and block for one screen; [viewerId] hides them on the player's own content. */
class FeedSafety(val vm: ContentSafetyViewModel, val viewerId: Int?)

@Composable
fun rememberFeedSafety(graph: AppGraph): FeedSafety {
    val vm = rememberShared { graph.contentSafety() }
    val auth by graph.data.auth.state.collectAsStateWithLifecycle()
    return FeedSafety(vm, (auth as? AuthState.SignedIn)?.user?.id)
}

/** The report and block dialogs. [onBlocked] leaves or reloads the screen so the blocked player disappears. */
@Composable
fun ModerationHost(vm: ContentSafetyViewModel, onBlocked: () -> Unit) {
    val s by vm.state.collectAsStateWithLifecycle()
    val message by vm.message.collectAsStateWithLifecycle()
    val context = LocalContext.current
    LaunchedEffect(message) {
        message?.let {
            Toast.makeText(context, it.text, Toast.LENGTH_LONG).show()
            vm.messageShown()
        }
    }
    LaunchedEffect(s.blockedUserId) {
        if (s.blockedUserId != null) {
            vm.blockHandled()
            onBlocked()
        }
    }
    when (val prompt = s.prompt) {
        null -> Unit
        is SafetyPrompt.Report -> ReportDialog(onPick = vm::report, onDismiss = vm::dismiss)
        is SafetyPrompt.Block -> ConfirmDialog(
            title = "Block ${prompt.name}?",
            body = "You won't see each other's posts, comments or messages. You can undo this in Settings.",
            confirm = "Block",
            onConfirm = vm::confirmBlock,
            dismiss = "Cancel",
            onDismiss = vm::dismiss,
            destructive = true,
        )
    }
}

@Composable
private fun ReportDialog(onPick: (ContentReportReason) -> Unit, onDismiss: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = OsirisColors.Surface,
        title = { Text("Why are you reporting this?") },
        text = {
            Column {
                for (reason in ContentReportReason.entries) {
                    ListItem(
                        headlineContent = { Text(reason.label) },
                        colors = ListItemDefaults.colors(containerColor = Color.Transparent),
                        modifier = Modifier.clickable { onPick(reason) },
                    )
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

/** A three-dot menu with Report and Block items. */
@Composable
private fun SafetyMenu(reportLabel: String, description: String, onReport: () -> Unit, blockName: String, onBlock: () -> Unit) {
    var open by remember { mutableStateOf(false) }
    Box {
        IconButton(onClick = { open = true }) { Icon(Icons.Outlined.MoreVert, contentDescription = description) }
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            DropdownMenuItem(text = { Text(reportLabel) }, onClick = {
                open = false
                onReport()
            })
            DropdownMenuItem(text = { Text("Block $blockName", color = OsirisColors.Error) }, onClick = {
                open = false
                onBlock()
            })
        }
    }
}

@Composable
fun UserSafetyMenu(userId: Int, name: String, vm: ContentSafetyViewModel) = SafetyMenu(
    reportLabel = "Report player",
    description = "Report or block $name",
    onReport = { vm.askReport(ReportKind.USER, userId) },
    blockName = name,
    onBlock = { vm.askBlock(userId, name) },
)

@Composable
fun PostSafetyMenu(post: FeedPost, vm: ContentSafetyViewModel) = SafetyMenu(
    reportLabel = "Report post",
    description = "Report or block ${post.authorName}",
    onReport = { vm.askReport(ReportKind.POST, post.id) },
    blockName = post.authorName,
    onBlock = { vm.askBlock(post.userId, post.authorName) },
)

@Composable
fun CommentSafetyMenu(comment: PostCommentItem, vm: ContentSafetyViewModel) = SafetyMenu(
    reportLabel = "Report comment",
    description = "Report or block ${comment.authorName}",
    onReport = { vm.askReport(ReportKind.COMMENT, comment.id) },
    blockName = comment.authorName,
    onBlock = { vm.askBlock(comment.userId, comment.authorName) },
)
