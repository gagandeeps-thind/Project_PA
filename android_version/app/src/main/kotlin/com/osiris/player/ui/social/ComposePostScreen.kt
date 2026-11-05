package com.osiris.player.ui.social

import android.graphics.BitmapFactory
import android.util.Base64
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.BarChart
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.FitnessCenter
import androidx.compose.material.icons.outlined.Image
import androidx.compose.material.icons.outlined.RadioButtonUnchecked
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.osiris.player.ui.arise.photoForUpload
import com.osiris.player.ui.common.OsirisScaffold
import com.osiris.player.ui.common.SectionHeader
import com.osiris.player.ui.common.localMinute
import com.osiris.player.ui.common.rememberShared
import com.osiris.player.ui.design.FrostCard
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.domain.common.Format
import com.osiris.shared.domain.model.SocialPostDraft
import com.osiris.shared.domain.model.TrainingSession
import com.osiris.shared.presentation.AppGraph
import com.osiris.shared.presentation.common.Loadable
import com.osiris.shared.presentation.social.ComposeState
import kotlinx.coroutines.launch

/** The + composer: a photo, up to four past workouts with their stats, a progress chart, or all together. */
@Composable
fun ComposePostScreen(graph: AppGraph, onDone: () -> Unit) {
    val vm = rememberShared { graph.composePost() }
    val s by vm.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val pick = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        if (uri != null) scope.launch { vm.photo(photoForUpload(context, uri)) }
    }
    LaunchedEffect(s.posted) { if (s.posted != null) onDone() }

    OsirisScaffold(
        "New post",
        vm,
        onBack = onDone,
        actions = {
            if (s.posting) {
                CircularProgressIndicator(Modifier.size(24.dp).padding(end = 8.dp))
            } else {
                TextButton(onClick = vm::post, enabled = s.canPost) { Text("Share", fontWeight = FontWeight.Bold) }
            }
        },
    ) { padding ->
        LazyColumn(
            Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            item {
                OutlinedTextField(
                    value = s.caption,
                    onValueChange = vm::caption,
                    placeholder = { Text("Write a caption… how did it feel?") },
                    minLines = 2,
                    modifier = Modifier.fillMaxWidth(),
                    supportingText = { Text("${s.caption.length}/${ComposeState.MAX_CAPTION}") },
                )
            }
            item {
                PhotoPicker(
                    s.photo,
                    onPick = { pick.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)) },
                    onClear = { vm.photo(null) },
                )
            }
            item { ChartToggle(s.withChart, vm::toggleChart) }
            item {
                Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
                    FollowersOnlyIcon()
                    Spacer(Modifier.width(8.dp))
                    Column(Modifier.weight(1f)) {
                        Text("Followers only")
                        Text("Off: anyone can find it in Discover", fontSize = 11.sp, color = OsirisColors.Faint)
                    }
                    Switch(checked = s.followersOnly, onCheckedChange = vm::followersOnly)
                }
            }
            item {
                SectionHeader(
                    "Attach workouts (${s.selected.size}/${SocialPostDraft.MAX_WORKOUTS}) · stats are verified by Osiris",
                    Modifier.padding(start = 0.dp),
                )
            }
            when (val sessions = s.sessions) {
                Loadable.Loading -> item { CircularProgressIndicator(Modifier.padding(16.dp)) }
                is Loadable.Failed -> item { Text(sessions.message, color = OsirisColors.Error) }
                is Loadable.Ready -> {
                    if (sessions.value.isEmpty()) {
                        item { Text("No saved workouts yet. Finish one on the Start tab to attach it.", color = OsirisColors.Faint) }
                    }
                    items(sessions.value, key = { it.id }) { session ->
                        SessionRow(session, s.activityName(session.activityKey), session.id in s.selected) { vm.toggleSession(session.id) }
                    }
                }
            }
        }
    }
}

@Composable
private fun PhotoPicker(photo: String?, onPick: () -> Unit, onClear: () -> Unit) {
    val preview: ImageBitmap? = remember(photo) {
        photo?.let { runCatching { Base64.decode(it, Base64.NO_WRAP) }.getOrNull() }
            ?.let { BitmapFactory.decodeByteArray(it, 0, it.size)?.asImageBitmap() }
    }
    if (preview == null) {
        FrostCard(onClick = onPick, modifier = Modifier.fillMaxWidth()) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Outlined.Image, null, tint = OsirisColors.Primary)
                Spacer(Modifier.width(12.dp))
                Column {
                    Text("Add a photo", fontWeight = FontWeight.SemiBold)
                    Text("Post-workout selfie, the view from the summit…", fontSize = 12.sp, color = OsirisColors.Faint)
                }
            }
        }
    } else {
        Box(Modifier.fillMaxWidth().aspectRatio(1f)) {
            Image(preview, "Selected photo", modifier = Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
            IconButton(
                onClick = onClear,
                modifier = Modifier.align(Alignment.TopEnd).padding(8.dp)
                    .background(OsirisColors.Background.copy(alpha = 0.7f), RoundedCornerShape(50)),
            ) { Icon(Icons.Outlined.Close, contentDescription = "Remove photo") }
        }
    }
}

@Composable
private fun ChartToggle(on: Boolean, onToggle: () -> Unit) {
    FrostCard(onClick = onToggle, modifier = Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Outlined.BarChart, null, tint = OsirisColors.Primary)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text("Add my progress chart", fontWeight = FontWeight.SemiBold)
                Text("Training minutes for the last 8 weeks", fontSize = 12.sp, color = OsirisColors.Faint)
            }
            Switch(checked = on, onCheckedChange = { onToggle() })
        }
    }
}

@Composable
private fun SessionRow(session: TrainingSession, name: String, selected: Boolean, onToggle: () -> Unit) {
    val stats = buildList {
        if (session.distanceM > 0) add(Format.distance(session.distanceM))
        add(Format.duration(session.durationS))
        if (session.reps > 0) add("${session.reps} reps")
        session.hrAvg?.let { add("${it.toInt()} bpm") }
    }.joinToString("  ·  ")
    Row(
        Modifier.fillMaxWidth()
            .border(1.dp, if (selected) OsirisColors.Primary else OsirisColors.Faint.copy(alpha = 0.25f), RoundedCornerShape(14.dp))
            .clickable(onClick = onToggle)
            .padding(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(Icons.Outlined.FitnessCenter, null, tint = OsirisColors.Secondary)
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(name, fontWeight = FontWeight.SemiBold)
                if (session.isPr) Text("  PR", color = OsirisColors.Gold, fontWeight = FontWeight.Bold, fontSize = 12.sp)
                if (session.posted) Text("  · posted", color = OsirisColors.Faint, fontSize = 12.sp)
            }
            Text(stats, style = MaterialTheme.typography.bodySmall, color = OsirisColors.Muted)
            Text(session.startedAt.localMinute(), fontSize = 11.sp, color = OsirisColors.Faint)
        }
        Icon(
            if (selected) Icons.Outlined.CheckCircle else Icons.Outlined.RadioButtonUnchecked,
            contentDescription = if (selected) "Attached" else "Attach",
            tint = if (selected) OsirisColors.Primary else OsirisColors.Faint,
        )
    }
}
