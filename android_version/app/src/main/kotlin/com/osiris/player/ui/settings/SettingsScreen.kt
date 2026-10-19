package com.osiris.player.ui.settings

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Logout
import androidx.compose.material.icons.automirrored.filled.Rule
import androidx.compose.material.icons.filled.Block
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material.icons.filled.DeleteForever
import androidx.compose.material.icons.filled.DevicesOther
import androidx.compose.material.icons.outlined.Badge
import androidx.compose.material.icons.outlined.Download
import androidx.compose.material.icons.outlined.FlagCircle
import androidx.compose.material.icons.outlined.LocationCity
import androidx.compose.material.icons.outlined.PersonAddAlt
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.osiris.player.platform.share.ShareEffect
import com.osiris.player.ui.common.ConfirmDialog
import com.osiris.player.ui.common.LoadableContent
import com.osiris.player.ui.common.OsirisScaffold
import com.osiris.player.ui.common.TextInputDialog
import com.osiris.player.ui.common.rememberShared
import com.osiris.player.ui.exercise.ExerciseConsentSheet
import com.osiris.player.ui.exercise.WithdrawExerciseConsentDialog
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.domain.model.Goal
import com.osiris.shared.domain.model.PlayerProfile
import com.osiris.shared.presentation.AppGraph
import com.osiris.shared.presentation.common.Loadable
import com.osiris.shared.presentation.settings.SettingsState
import com.osiris.shared.presentation.settings.SettingsViewModel

/** The dialog or sheet open on the settings screen. */
private enum class Open { NAME, GOAL, CITY, EXERCISE_ON, EXERCISE_OFF, BLOCKS, RULES, ERASE, ERASE_PASSWORD }

@Composable
fun SettingsScreen(graph: AppGraph, onBack: () -> Unit) {
    val vm = rememberShared { graph.settings() }
    val s by vm.state.collectAsStateWithLifecycle()
    var open by remember { mutableStateOf<Open?>(null) }
    ShareEffect(s.share, vm::shared)

    OsirisScaffold("SETTINGS", vm, onBack = onBack) { padding ->
        LoadableContent(s.profile, onRetry = vm::refresh, modifier = Modifier.padding(padding)) { p ->
            Settings(p, s, vm, Modifier.padding(padding)) { open = it }
        }
    }

    val profile = s.profile.valueOrNull
    val close = { open = null }
    when (open) {
        null -> Unit
        Open.NAME -> TextInputDialog("Your name", null, "Name", "SAVE", { vm.setDisplayName(it); close() }, "CANCEL", close, initial = profile?.displayName.orEmpty(), maxLength = 30)
        Open.CITY -> TextInputDialog("Home city", null, "City, e.g. Bedford NS", "SAVE", { vm.setCity(it); close() }, "CANCEL", close, initial = profile?.city.orEmpty())
        Open.GOAL -> GoalDialog(Goal.fromWire(profile?.goal ?: Goal.FITNESS.wire), onPick = { vm.setGoal(it); close() }, onDismiss = close)
        Open.EXERCISE_ON -> ExerciseConsentSheet { allow -> if (allow) vm.setExerciseConsent(true); close() }
        Open.EXERCISE_OFF -> WithdrawExerciseConsentDialog(
            onKeep = { vm.setExerciseConsent(false); close() },
            onDelete = { vm.setExerciseConsent(false, deleteData = true); close() },
            onCancel = close,
        )
        Open.BLOCKS -> BlocksSheet(s, vm, close)
        Open.RULES -> RulesSheet(s, close)
        Open.ERASE -> ConfirmDialog(
            title = "Erase your account?",
            body = "This deletes your routes, runs, badges, and profile. It cannot be undone. Other players keep their own results.",
            confirm = "ERASE",
            onConfirm = { open = Open.ERASE_PASSWORD },
            dismiss = "KEEP MY ACCOUNT",
            onDismiss = close,
            destructive = true,
        )
        Open.ERASE_PASSWORD -> TextInputDialog(
            "Confirm with your password", null, "Password", "ERASE",
            { if (it.isNotEmpty()) vm.erase(it); close() }, "CANCEL", close, maxLength = 128, secret = true,
        )
    }
}

@Composable
private fun Settings(p: PlayerProfile, s: SettingsState, vm: SettingsViewModel, modifier: Modifier, open: (Open) -> Unit) {
    LazyColumn(modifier.fillMaxSize()) {
        item { Header("Profile") }
        item { Row(Icons.Outlined.Badge, p.displayName, "Name others see") { open(Open.NAME) } }
        item { Row(Icons.Outlined.FlagCircle, Goal.fromWire(p.goal).label, s.identityLine) { open(Open.GOAL) } }
        item { Row(Icons.Outlined.LocationCity, p.city ?: "Not set", "Home city, used for local rankings (never from GPS)") { open(Open.CITY) } }

        item { Header("Privacy") }
        item { Toggle("Location during runs", "Needed to record and verify runs", p.locationConsent, vm::setLocationConsent) }
        item { Toggle("Show my name on leaderboards", "When off, you appear as \"Private runner\"", p.leaderboardOptIn, vm::setLeaderboardOptIn) }
        item { Toggle("Public achievement page", "Shows your rank, runs, and badges. Never your location.", p.publicProfile, vm::setPublicProfile) }
        item {
            Toggle("Camera exercise counting", "Counts reps on this phone; keeps rep counts and timings", s.exerciseConsent) { on ->
                open(if (on) Open.EXERCISE_ON else Open.EXERCISE_OFF)
            }
        }

        item { Header("Invite friends") }
        item {
            when (val r = s.referral) {
                Loadable.Loading -> LinearProgressIndicator(Modifier.fillMaxWidth().padding(16.dp))
                is Loadable.Failed -> ListItem(headlineContent = { Text(r.message) }, colors = clear())
                is Loadable.Ready -> Column {
                    ListItem(
                        leadingContent = { Icon(Icons.Outlined.PersonAddAlt, null) },
                        headlineContent = { Text("Your invite code: ${r.value.code}") },
                        supportingContent = { Text("${r.value.rewarded} friends rewarded  •  ${r.value.pending} waiting for their first run") },
                        trailingContent = { IconButton(onClick = vm::shareInvite) { Icon(Icons.Filled.ContentCopy, "Share invite link") } },
                        colors = clear(),
                    )
                    for (rule in r.value.rules) {
                        Text(rule, color = OsirisColors.Faint, fontSize = 12.sp, modifier = Modifier.padding(start = 72.dp, end = 16.dp, bottom = 4.dp))
                    }
                }
            }
        }

        item { Header("Safety") }
        item { Row(Icons.Filled.Block, "Blocked players") { vm.loadBlocks(); open(Open.BLOCKS) } }
        item { Row(Icons.AutoMirrored.Filled.Rule, "Rules, rewards, and verification") { vm.loadRules(); open(Open.RULES) } }

        item { Header("Account") }
        item { Row(Icons.Filled.DevicesOther, "Sign out of all other devices", onClick = vm::signOutEverywhere) }
        item { Row(Icons.Outlined.Download, "Download my data", onClick = vm::exportData) }
        item { Row(Icons.AutoMirrored.Filled.Logout, "Log out", onClick = vm::logout) }
        item { Row(Icons.Filled.DeleteForever, "Erase my account", color = OsirisColors.Error) { open(Open.ERASE) } }
        item { Spacer(Modifier.height(24.dp)) }
    }
}

@Composable
private fun clear() = ListItemDefaults.colors(containerColor = Color.Transparent)

@Composable
private fun Header(text: String) {
    Text(
        text.uppercase(),
        color = OsirisColors.Secondary,
        fontSize = 12.sp,
        letterSpacing = 1.2.sp,
        modifier = Modifier.padding(start = 16.dp, top = 20.dp, end = 16.dp, bottom = 4.dp),
    )
}

@Composable
private fun Row(icon: ImageVector, title: String, subtitle: String? = null, color: Color = Color.Unspecified, onClick: () -> Unit) {
    ListItem(
        leadingContent = { Icon(icon, null, tint = if (color == Color.Unspecified) Color.White else color) },
        headlineContent = { Text(title, color = color) },
        supportingContent = if (subtitle != null) { { Text(subtitle) } } else null,
        colors = clear(),
        modifier = Modifier.clickable(onClick = onClick),
    )
}

@Composable
private fun Toggle(title: String, subtitle: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    ListItem(
        headlineContent = { Text(title) },
        supportingContent = { Text(subtitle) },
        trailingContent = { Switch(checked = checked, onCheckedChange = onChange) },
        colors = clear(),
        modifier = Modifier.clickable { onChange(!checked) },
    )
}

@Composable
private fun GoalDialog(current: Goal, onPick: (Goal) -> Unit, onDismiss: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = OsirisColors.Surface,
        title = { Text("Your goal") },
        text = {
            Column {
                for (g in Goal.entries) {
                    ListItem(
                        headlineContent = { Text(g.label, color = if (g == current) OsirisColors.Secondary else Color.Unspecified) },
                        supportingContent = { Text(g.description) },
                        colors = clear(),
                        modifier = Modifier.clickable { onPick(g) },
                    )
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("CANCEL") } },
    )
}

@Composable
private fun BlocksSheet(s: SettingsState, vm: SettingsViewModel, onDismiss: () -> Unit) {
    ModalBottomSheet(onDismissRequest = onDismiss, containerColor = OsirisColors.Surface) {
        Column(Modifier.padding(16.dp).navigationBarsPadding()) {
            Text("Blocked players", fontSize = 18.sp)
            val blocks = s.blocks
            when {
                blocks == null -> LinearProgressIndicator(Modifier.fillMaxWidth().padding(12.dp))
                blocks.isEmpty() -> Text("You haven't blocked anyone.", Modifier.padding(12.dp))
                else -> for (b in blocks) {
                    ListItem(
                        headlineContent = { Text(b.name) },
                        trailingContent = { TextButton(onClick = { vm.unblock(b.id) }) { Text("UNBLOCK") } },
                        colors = clear(),
                    )
                }
            }
        }
    }
}

@Composable
private fun RulesSheet(s: SettingsState, onDismiss: () -> Unit) {
    ModalBottomSheet(onDismissRequest = onDismiss, containerColor = OsirisColors.Surface) {
        Column(Modifier.verticalScroll(rememberScrollState()).padding(16.dp).navigationBarsPadding()) {
            Text("RULES", style = MaterialTheme.typography.titleLarge)
            val rules = s.rules
            if (rules == null) LinearProgressIndicator(Modifier.fillMaxWidth().padding(12.dp))
            for (section in rules.orEmpty()) {
                Text(section.title, style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(top = 16.dp))
                for (line in section.lines) Text("•  $line", Modifier.padding(vertical = 4.dp))
            }
        }
    }
}
