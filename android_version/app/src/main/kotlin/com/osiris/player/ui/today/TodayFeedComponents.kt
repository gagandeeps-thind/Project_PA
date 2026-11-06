package com.osiris.player.ui.today

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.Comment
import androidx.compose.material.icons.automirrored.outlined.Send
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.outlined.AutoAwesome
import androidx.compose.material.icons.outlined.Diamond
import androidx.compose.material.icons.outlined.LocalFireDepartment
import androidx.compose.material.icons.outlined.Map
import androidx.compose.material.icons.outlined.Share
import androidx.compose.material.icons.outlined.Verified
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.osiris.player.ui.design.FrostCard
import com.osiris.player.ui.design.bleed
import com.osiris.player.ui.design.KeyButton
import com.osiris.player.ui.design.RaisedButton
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.core.design.FrostMatte
import com.osiris.shared.domain.model.FeedPost
import com.osiris.shared.domain.model.NotificationItem
import com.osiris.shared.domain.model.PostCommentItem
import com.osiris.shared.domain.model.PostCreateDraft
import com.osiris.shared.domain.model.SuggestedOsirian
import com.osiris.shared.domain.model.WorkoutPlan

@Composable
fun SuggestedOsiriansSection(
    osirians: List<SuggestedOsirian>,
    onFollowToggle: (SuggestedOsirian) -> Unit,
    onDismiss: (Int) -> Unit,
    onSeeAll: () -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(1f)) {
                Text("Suggested Osirians", style = MaterialTheme.typography.titleMedium)
                Text(
                    "Athletes trending for verified workouts & claimed domains",
                    style = MaterialTheme.typography.bodySmall,
                    color = OsirisColors.Faint,
                )
            }
            TextButton(onClick = onSeeAll) {
                Text("See All", color = OsirisColors.Primary, fontWeight = FontWeight.SemiBold)
            }
        }
        if (osirians.isEmpty()) {
            FrostCard(contentPadding = 16.dp) {
                Text(
                    "No more suggestions right now. Tap See All to view trending Osirians.",
                    style = MaterialTheme.typography.bodySmall,
                    color = OsirisColors.Muted,
                )
            }
        } else {
            LazyRow(
                modifier = Modifier.bleed(20.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                contentPadding = PaddingValues(horizontal = 20.dp, vertical = 16.dp),
            ) {
                items(osirians, key = { it.userId }) { person ->
                    OsirianCard(
                        person = person,
                        onFollowToggle = { onFollowToggle(person) },
                        onDismiss = { onDismiss(person.userId) },
                    )
                }
            }
        }
    }
}

@Composable
private fun OsirianCard(
    person: SuggestedOsirian,
    onFollowToggle: () -> Unit,
    onDismiss: () -> Unit,
) {
    FrostCard(
        modifier = Modifier.width(168.dp),
        radius = FrostMatte.Radius.MEDIUM,
        contentPadding = 12.dp,
    ) {
        Box(Modifier.fillMaxWidth()) {
            IconButton(
                onClick = onDismiss,
                modifier = Modifier.size(24.dp).align(Alignment.TopEnd),
            ) {
                Icon(
                    Icons.Filled.Close,
                    contentDescription = "Dismiss ${person.displayName}",
                    modifier = Modifier.size(16.dp),
                    tint = OsirisColors.Faint,
                )
            }
            Column(
                modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Box(
                    modifier = Modifier
                        .size(56.dp)
                        .clip(CircleShape)
                        .background(OsirisColors.Primary.copy(alpha = 0.18f))
                        .border(1.5.dp, OsirisColors.Secondary, CircleShape),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        person.initials,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        color = OsirisColors.Secondary,
                    )
                }
                Spacer(Modifier.height(8.dp))
                Text(
                    person.displayName,
                    style = MaterialTheme.typography.titleSmall,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    textAlign = TextAlign.Center,
                )
                Text(
                    "${person.rank} · ${person.title}",
                    style = MaterialTheme.typography.labelSmall,
                    color = OsirisColors.Secondary,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Spacer(Modifier.height(4.dp))
                Text(
                    person.trendingReason.ifBlank { "${person.xp} XP" },
                    style = MaterialTheme.typography.bodySmall,
                    color = OsirisColors.Faint,
                    fontSize = 11.sp,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    textAlign = TextAlign.Center,
                )
                Spacer(Modifier.height(10.dp))
                if (person.following) {
                    RaisedButton(
                        onClick = onFollowToggle,
                        modifier = Modifier.fillMaxWidth().height(36.dp),
                    ) {
                        Text("Following", fontSize = 12.sp)
                    }
                } else {
                    KeyButton(
                        onClick = onFollowToggle,
                        modifier = Modifier.fillMaxWidth().height(36.dp),
                    ) {
                        Text("Follow", fontSize = 12.sp)
                    }
                }
            }
        }
    }
}

@Suppress("CyclomaticComplexMethod")
@Composable
fun PostCard(
    post: FeedPost,
    onReact: (String) -> Unit,
    onOpenComments: () -> Unit,
    onShare: () -> Unit,
    media: (@Composable () -> Unit)? = null,
) {
    FrostCard(radius = FrostMatte.Radius.MEDIUM, contentPadding = 16.dp) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                modifier = Modifier
                    .size(42.dp)
                    .clip(CircleShape)
                    .background(OsirisColors.Primary.copy(alpha = 0.2f))
                    .border(1.dp, OsirisColors.Secondary.copy(alpha = 0.7f), CircleShape),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    post.authorInitials,
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold,
                    color = OsirisColors.Secondary,
                )
            }
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(post.authorName, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                    Spacer(Modifier.width(6.dp))
                    Text(
                        "${post.authorRank} · ${post.authorTitle}",
                        style = MaterialTheme.typography.labelSmall,
                        color = OsirisColors.Secondary,
                    )
                }
                Text(
                    "@${post.authorHandle}  •  ${post.kindBadgeLabel}",
                    style = MaterialTheme.typography.bodySmall,
                    color = OsirisColors.Faint,
                    fontSize = 11.sp,
                )
            }
        }

        if (media != null) {
            Spacer(Modifier.height(12.dp))
            media()
        }

        post.summary.measureLabel?.takeIf { it.isNotBlank() && media == null }?.let { measure ->
            Spacer(Modifier.height(12.dp))
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(OsirisColors.Primary.copy(alpha = 0.12f), RoundedCornerShape(12.dp))
                    .border(1.dp, OsirisColors.Primary.copy(alpha = 0.35f), RoundedCornerShape(12.dp))
                    .padding(horizontal = 14.dp, vertical = 10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                val icon = when (post.kind) {
                    "domain_claim" -> Icons.Outlined.Map
                    "streak" -> Icons.Outlined.LocalFireDepartment
                    "crystal_earn" -> Icons.Outlined.Diamond
                    else -> Icons.Outlined.Verified
                }
                Icon(icon, null, tint = OsirisColors.Secondary, modifier = Modifier.size(20.dp))
                Spacer(Modifier.width(10.dp))
                Column(Modifier.weight(1f)) {
                    Text(measure, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                    val extras = buildList {
                        if (post.summary.xpEarned > 0) add("+${post.summary.xpEarned} XP")
                        if (post.summary.crystalsEarned > 0) add("+${post.summary.crystalsEarned} Mana Crystals")
                        if (post.summary.domainAreaSqkm > 0) add("${post.summary.domainAreaSqkm} km² Domain")
                        if (post.summary.streakDays > 0) add("${post.summary.streakDays}d Streak")
                    }
                    if (extras.isNotEmpty()) {
                        Text(
                            extras.joinToString("  •  "),
                            style = MaterialTheme.typography.bodySmall,
                            color = OsirisColors.Muted,
                            fontSize = 11.sp,
                        )
                    }
                }
            }
        }

        if (post.caption.isNotBlank()) {
            Spacer(Modifier.height(10.dp))
            Text(post.caption, style = MaterialTheme.typography.bodyMedium)
        }

        Spacer(Modifier.height(12.dp))
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            val reactions = listOf(
                "fire" to "🔥",
                "like" to "❤️",
                "clap" to "👏",
                "crown" to "👑",
            )
            reactions.forEach { (key, emoji) ->
                val active = post.myReaction == key
                val count = post.reactionCount(key)
                Box(
                    modifier = Modifier
                        .clip(RoundedCornerShape(16.dp))
                        .background(if (active) OsirisColors.Primary.copy(alpha = 0.28f) else OsirisColors.Background.copy(alpha = 0.5f))
                        .border(
                            1.dp,
                            if (active) OsirisColors.Primary else OsirisColors.Faint.copy(alpha = 0.3f),
                            RoundedCornerShape(16.dp),
                        )
                        .clickable { onReact(key) }
                        .padding(horizontal = 9.dp, vertical = 5.dp),
                ) {
                    Text(
                        if (count > 0) "$emoji $count" else emoji,
                        fontSize = 12.sp,
                        color = if (active) OsirisColors.Secondary else OsirisColors.Muted,
                    )
                }
            }
            Spacer(Modifier.weight(1f))
            TextButton(onClick = onOpenComments, contentPadding = PaddingValues(horizontal = 8.dp, vertical = 4.dp)) {
                Icon(Icons.AutoMirrored.Outlined.Comment, null, modifier = Modifier.size(16.dp))
                Spacer(Modifier.width(4.dp))
                Text("${post.commentCount}", fontSize = 12.sp)
            }
            TextButton(onClick = onShare, contentPadding = PaddingValues(horizontal = 8.dp, vertical = 4.dp)) {
                Icon(Icons.Outlined.Share, null, modifier = Modifier.size(16.dp))
                Spacer(Modifier.width(4.dp))
                Text(if (post.shareCount > 0) "${post.shareCount}" else "Share", fontSize = 12.sp)
            }
        }

        if (post.recentComments.isNotEmpty()) {
            Spacer(Modifier.height(6.dp))
            HorizontalDivider(color = OsirisColors.Faint.copy(alpha = 0.2f))
            Spacer(Modifier.height(6.dp))
            post.recentComments.takeLast(2).forEach { c ->
                Text(
                    "${c.authorName}: ${c.body}",
                    style = MaterialTheme.typography.bodySmall,
                    color = OsirisColors.Muted,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}

@Composable
fun NotificationsSheet(
    notifications: List<NotificationItem>,
    onMarkRead: (Int) -> Unit,
    onMarkAllRead: () -> Unit,
    onOpenRoute: (String) -> Unit,
    onDismiss: () -> Unit,
) {
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = OsirisColors.Surface,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp, vertical = 12.dp)
                .navigationBarsPadding(),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Filled.Notifications, null, tint = OsirisColors.Primary)
                Spacer(Modifier.width(8.dp))
                Text("Osiris Notifications", style = MaterialTheme.typography.titleLarge, modifier = Modifier.weight(1f))
                if (notifications.any { !it.read }) {
                    TextButton(onClick = onMarkAllRead) { Text("Mark all read") }
                }
            }
            Text(
                "Feature suggestions, app updates, new followers, and community reactions.",
                style = MaterialTheme.typography.bodySmall,
                color = OsirisColors.Muted,
            )
            if (notifications.isEmpty()) {
                Text("You're all caught up!", color = OsirisColors.Faint, modifier = Modifier.padding(vertical = 24.dp))
            } else {
                notifications.forEach { n ->
                    FrostCard(
                        onClick = {
                            if (!n.read) onMarkRead(n.id)
                            n.actionRoute?.takeIf { it.isNotBlank() }?.let { route ->
                                onDismiss()
                                onOpenRoute(route)
                            }
                        },
                        fill = if (n.read) OsirisColors.Background.copy(alpha = 0.45f) else OsirisColors.Primary.copy(alpha = 0.16f),
                        contentPadding = 14.dp,
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(
                                Icons.Outlined.AutoAwesome,
                                null,
                                tint = if (n.read) OsirisColors.Faint else OsirisColors.Secondary,
                                modifier = Modifier.size(18.dp),
                            )
                            Spacer(Modifier.width(8.dp))
                            Text(
                                n.title,
                                style = MaterialTheme.typography.titleSmall,
                                fontWeight = if (n.read) FontWeight.Normal else FontWeight.Bold,
                                modifier = Modifier.weight(1f),
                            )
                            if (!n.read) {
                                Box(Modifier.size(8.dp).clip(CircleShape).background(OsirisColors.Secondary))
                            }
                        }
                        Spacer(Modifier.height(4.dp))
                        Text(n.body, style = MaterialTheme.typography.bodySmall, color = OsirisColors.Muted)
                    }
                }
            }
            Spacer(Modifier.height(12.dp))
        }
    }
}

@Composable
fun TrendingOsiriansSheet(
    osirians: List<SuggestedOsirian>,
    onFollowToggle: (SuggestedOsirian) -> Unit,
    onDismiss: () -> Unit,
) {
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = OsirisColors.Surface,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp, vertical = 12.dp)
                .navigationBarsPadding(),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text("Influential & Trending Osirians", style = MaterialTheme.typography.titleLarge)
            Text(
                "Ranked by verified workouts, active streaks, XP, and claimed domains.",
                style = MaterialTheme.typography.bodySmall,
                color = OsirisColors.Muted,
            )
            osirians.forEach { person ->
                FrostCard(contentPadding = 14.dp) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(
                            modifier = Modifier
                                .size(44.dp)
                                .clip(CircleShape)
                                .background(OsirisColors.Primary.copy(alpha = 0.2f))
                                .border(1.dp, OsirisColors.Secondary, CircleShape),
                            contentAlignment = Alignment.Center,
                        ) {
                            Text(person.initials, fontWeight = FontWeight.Bold, color = OsirisColors.Secondary)
                        }
                        Spacer(Modifier.width(12.dp))
                        Column(Modifier.weight(1f)) {
                            Text(person.displayName, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                            Text(
                                "${person.rank} · ${person.title} · ${person.xp} XP",
                                style = MaterialTheme.typography.labelSmall,
                                color = OsirisColors.Secondary,
                            )
                            Text(
                                person.trendingReason,
                                style = MaterialTheme.typography.bodySmall,
                                color = OsirisColors.Faint,
                                fontSize = 11.sp,
                            )
                        }
                        if (person.following) {
                            RaisedButton(onClick = { onFollowToggle(person) }, modifier = Modifier.height(36.dp)) {
                                Text("Following", fontSize = 12.sp)
                            }
                        } else {
                            KeyButton(onClick = { onFollowToggle(person) }, modifier = Modifier.height(36.dp)) {
                                Text("Follow", fontSize = 12.sp)
                            }
                        }
                    }
                }
            }
            Spacer(Modifier.height(12.dp))
        }
    }
}

@Suppress("CyclomaticComplexMethod")
@Composable
fun PostComposerSheet(
    plan: WorkoutPlan,
    streakWeeks: Int,
    onPublish: (PostCreateDraft) -> Unit,
    onDismiss: () -> Unit,
) {
    var selectedKind by remember { mutableStateOf("workout") }
    var caption by remember { mutableStateOf("") }
    var sets by remember { mutableIntStateOf(plan.sets) }
    var reps by remember { mutableIntStateOf(plan.repsPerSet) }
    var domainSqKm by remember { mutableStateOf("0.45") }
    var crystals by remember { mutableIntStateOf(25) }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = OsirisColors.Surface,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp, vertical = 12.dp)
                .navigationBarsPadding(),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text("Post to People's Posts", style = MaterialTheme.typography.titleLarge)
            Text(
                "Share your camera-verified workouts, claimed domains, streaks, or Mana Crystal earnings.",
                style = MaterialTheme.typography.bodySmall,
                color = OsirisColors.Muted,
            )
            val kinds = listOf(
                "workout" to "Workout",
                "domain_claim" to "Claimed Domain",
                "streak" to "Streak",
                "crystal_earn" to "Crystals",
                "run" to "GPS Run",
            )
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                items(kinds, key = { it.first }) { (k, label) ->
                    FilterChip(
                        selected = selectedKind == k,
                        onClick = { selectedKind = k },
                        label = { Text(label) },
                    )
                }
            }

            when (selectedKind) {
                "workout" -> {
                    Text(
                        "Exercise: ${plan.option.name} (${plan.measureLabel})",
                        style = MaterialTheme.typography.titleSmall,
                        color = OsirisColors.Secondary,
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        RaisedButton(onClick = { reps = (reps - 2).coerceAtLeast(1) }) { Text("- Reps") }
                        Text("$reps × $sets", modifier = Modifier.align(Alignment.CenterVertically), fontWeight = FontWeight.Bold)
                        RaisedButton(onClick = { reps += 2 }) { Text("+ Reps") }
                        RaisedButton(onClick = { sets = (sets % 10) + 1 }) { Text("Sets: $sets") }
                    }
                }
                "domain_claim" -> {
                    OutlinedTextField(
                        value = domainSqKm,
                        onValueChange = { domainSqKm = it },
                        label = { Text("Domain territory claimed (km²)") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
                "streak" -> {
                    Text(
                        "Active Streak: ${(streakWeeks.coerceAtLeast(1)) * 7} days (${streakWeeks.coerceAtLeast(1)} weeks)",
                        style = MaterialTheme.typography.titleSmall,
                        color = OsirisColors.Secondary,
                    )
                }
                "crystal_earn" -> {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        RaisedButton(onClick = { crystals = (crystals - 5).coerceAtLeast(5) }) { Text("-5") }
                        Text("+$crystals Mana Crystals", fontWeight = FontWeight.Bold)
                        RaisedButton(onClick = { crystals += 10 }) { Text("+10") }
                    }
                }
                else -> {
                    Text("GPS Distance: ${plan.targetDistanceKm} km", color = OsirisColors.Secondary)
                }
            }

            OutlinedTextField(
                value = caption,
                onValueChange = { caption = it },
                label = { Text("Caption (tell Osirians about your session)") },
                modifier = Modifier.fillMaxWidth(),
                minLines = 2,
                maxLines = 4,
            )

            KeyButton(
                onClick = {
                    val area = domainSqKm.toDoubleOrNull() ?: 0.45
                    val draft = when (selectedKind) {
                        "workout" -> PostCreateDraft(
                            kind = "workout",
                            caption = caption.ifBlank { "Crushed ${plan.option.name} — $reps × $sets with AI camera verification!" },
                            exerciseKey = if (plan.option.isCameraExercise) plan.optionKey else "pushup",
                            sets = sets,
                            repsPerSet = if (plan.option.isHold) 0 else reps,
                            totalReps = if (plan.option.isHold) 0 else reps * sets,
                            holdS = if (plan.option.isHold) (plan.holdSecondsPerSet * sets).toDouble() else 0.0,
                            xpEarned = sets * 15,
                        )
                        "domain_claim" -> PostCreateDraft(
                            kind = "domain_claim",
                            caption = caption.ifBlank { "Claimed a new $area km² domain loop on Osiris!" },
                            domainAreaSqkm = area,
                            distanceM = plan.targetDistanceKm * 1000.0,
                            xpEarned = 60,
                        )
                        "streak" -> PostCreateDraft(
                            kind = "streak",
                            caption = caption.ifBlank { "Keeping the Osiris streak alive!" },
                            streakDays = (streakWeeks.coerceAtLeast(1)) * 7,
                            xpEarned = 35,
                        )
                        "crystal_earn" -> PostCreateDraft(
                            kind = "crystal_earn",
                            caption = caption.ifBlank { "Earned +$crystals Mana Crystals from today's quests & challenges!" },
                            crystalsEarned = crystals,
                            xpEarned = 25,
                        )
                        else -> PostCreateDraft(
                            kind = "run",
                            caption = caption.ifBlank { "Completed a ${plan.targetDistanceKm} km GPS run!" },
                            distanceM = plan.targetDistanceKm * 1000.0,
                            durationS = plan.targetDistanceKm * 330.0,
                            xpEarned = 45,
                        )
                    }
                    onPublish(draft)
                },
                modifier = Modifier.fillMaxWidth().height(52.dp),
            ) {
                Text("Publish to People's Posts")
            }
            Spacer(Modifier.height(8.dp))
        }
    }
}

@Composable
fun CommentsSheet(
    comments: List<PostCommentItem>,
    onAddComment: (String) -> Unit,
    onDismiss: () -> Unit,
) {
    var text by remember { mutableStateOf("") }
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = OsirisColors.Surface,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp, vertical = 12.dp)
                .navigationBarsPadding(),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text("Comments", style = MaterialTheme.typography.titleLarge)
            if (comments.isEmpty()) {
                Text("Be the first Osirian to comment on this post.", color = OsirisColors.Muted)
            } else {
                comments.forEach { c ->
                    FrostCard(contentPadding = 12.dp) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(c.authorName, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                            Spacer(Modifier.width(6.dp))
                            Text(c.authorRank, style = MaterialTheme.typography.labelSmall, color = OsirisColors.Secondary)
                        }
                        Spacer(Modifier.height(4.dp))
                        Text(c.body, style = MaterialTheme.typography.bodyMedium)
                    }
                }
            }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = text,
                    onValueChange = { text = it },
                    placeholder = { Text("Add a comment…") },
                    singleLine = true,
                    modifier = Modifier.weight(1f),
                )
                IconButton(
                    onClick = {
                        if (text.isNotBlank()) {
                            onAddComment(text)
                            text = ""
                        }
                    },
                ) {
                    Icon(Icons.AutoMirrored.Outlined.Send, contentDescription = "Send comment", tint = OsirisColors.Primary)
                }
            }
            Spacer(Modifier.height(8.dp))
        }
    }
}
