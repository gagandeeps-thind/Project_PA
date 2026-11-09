package com.osiris.player.ui.social

import android.graphics.BitmapFactory
import android.util.LruCache
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.Comment
import androidx.compose.material.icons.filled.LocalFireDepartment
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.EmojiEvents
import androidx.compose.material.icons.outlined.LocalFireDepartment
import androidx.compose.material.icons.outlined.Lock
import androidx.compose.material.icons.outlined.MoreVert
import androidx.compose.material.icons.outlined.Share
import androidx.compose.material.icons.outlined.Verified
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.osiris.player.ui.design.FrostCard
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.core.design.FrostMatte
import com.osiris.shared.domain.common.Format
import com.osiris.shared.domain.model.ActiveFriend
import com.osiris.shared.domain.model.FeedPost
import com.osiris.shared.domain.model.PostAttachment
import com.osiris.shared.domain.model.PostChart
import java.net.URL
import kotlin.time.Instant
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/** The full URL of a photo path the API returned (`/api/v2/social/media/...`). */
fun mediaUrl(baseUrl: String, path: String): String = baseUrl.trimEnd('/') + path

/** Decoded post photos, so scrolling back up does not download them again. */
private val photoCache = LruCache<String, ImageBitmap>(PHOTO_CACHE_ENTRIES)

/** A post photo from [url], cached in memory; null while loading or if it fails. */
@Composable
fun rememberPostPhoto(url: String): ImageBitmap? {
    val image by produceState<ImageBitmap?>(photoCache.get(url), url) {
        if (value == null) {
            value = withContext(Dispatchers.IO) {
                runCatching { URL(url).openStream().use { BitmapFactory.decodeStream(it) }?.asImageBitmap() }.getOrNull()
            }?.also { photoCache.put(url, it) }
        }
    }
    return image
}

/** A round avatar with the player's initials; [ring] draws the "trained today" gradient ring. */
@Composable
fun Avatar(initials: String, size: Dp = 40.dp, ring: Boolean = false, onClick: (() -> Unit)? = null) {
    val ringBrush = Brush.linearGradient(listOf(OsirisColors.Primary, OsirisColors.Gold, OsirisColors.Secondary))
    val outer = Modifier
        .size(size)
        .clip(CircleShape)
        .then(if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier)
        .then(if (ring) Modifier.border(2.5.dp, ringBrush, CircleShape) else Modifier)
        .padding(if (ring) 4.dp else 0.dp)
    Box(outer, contentAlignment = Alignment.Center) {
        Box(
            Modifier.fillMaxWidth().aspectRatio(1f).clip(CircleShape).background(OsirisColors.Primary.copy(alpha = 0.22f)),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                initials,
                fontWeight = FontWeight.Bold,
                color = OsirisColors.Secondary,
                fontSize = (size.value * 0.34f).sp,
            )
        }
    }
}

/** Instagram's stories row: you first (opens the composer), then everyone you follow who trained today. */
@Composable
fun ActiveTodayRow(friends: List<ActiveFriend>, onCompose: () -> Unit, onOpen: (Int) -> Unit) {
    LazyRow(
        horizontalArrangement = Arrangement.spacedBy(14.dp),
        modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp),
    ) {
        item {
            StoryBubble("Your post", sub = "Share a workout", onClick = onCompose) {
                Box(
                    Modifier.size(64.dp).clip(CircleShape).background(OsirisColors.Surface)
                        .border(1.dp, OsirisColors.Faint.copy(alpha = 0.4f), CircleShape),
                    contentAlignment = Alignment.Center,
                ) { Icon(Icons.Outlined.Add, contentDescription = "New post", tint = OsirisColors.Primary) }
            }
        }
        items(friends, key = { it.userId }) { f ->
            StoryBubble(f.displayName.substringBefore(' '), sub = "${f.activityName} · ${f.minutes}m", onClick = { onOpen(f.userId) }) {
                Avatar(f.initials, size = 64.dp, ring = true)
            }
        }
    }
}

@Composable
private fun StoryBubble(name: String, sub: String, onClick: () -> Unit, avatar: @Composable () -> Unit) {
    Column(
        Modifier.width(76.dp).clickable(onClick = onClick),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        avatar()
        Spacer(Modifier.height(4.dp))
        Text(name, style = MaterialTheme.typography.labelMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
        Text(sub, fontSize = 10.sp, color = OsirisColors.Faint, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

/** What a post card can do. [onDelete] is null on other players' posts. */
class PostCallbacks(
    val onKudos: (Int) -> Unit,
    val onDoubleTap: (Int) -> Unit,
    val onComments: (Int) -> Unit,
    val onShare: (Int) -> Unit,
    val onAuthor: (Int) -> Unit,
    val onDelete: ((Int) -> Unit)?,
    val onReport: (Int) -> Unit,
    val onBlock: (FeedPost) -> Unit,
)

/** An Instagram-style post: header, media (photo, workouts, chart), actions, kudos, caption, comments. */
@Composable
fun SocialPostCard(post: FeedPost, baseUrl: String, now: Instant, isMine: Boolean, actions: PostCallbacks) {
    FrostCard(radius = FrostMatte.Radius.MEDIUM, contentPadding = 0.dp) {
        PostHeader(post, now, isMine, actions)
        Box(
            Modifier.fillMaxWidth().pointerInput(post.id) {
                detectTapGestures(onDoubleTap = { actions.onDoubleTap(post.id) })
            },
        ) { PostMedia(post, baseUrl) }
        PostActions(post, actions)
        PostText(post, actions)
    }
}

@Composable
private fun PostHeader(post: FeedPost, now: Instant, isMine: Boolean, actions: PostCallbacks) {
    var menu by remember { mutableStateOf(false) }
    Row(Modifier.fillMaxWidth().padding(start = 12.dp, top = 10.dp, bottom = 8.dp), verticalAlignment = Alignment.CenterVertically) {
        Avatar(post.authorInitials, size = 36.dp, onClick = { actions.onAuthor(post.userId) })
        Spacer(Modifier.width(10.dp))
        Column(Modifier.weight(1f).clickable { actions.onAuthor(post.userId) }) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(post.authorName, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold, maxLines = 1)
                post.createdInstant?.let {
                    Text(
                        "  ·  ${Format.ago((now - it).inWholeSeconds)}",
                        style = MaterialTheme.typography.bodySmall,
                        color = OsirisColors.Faint,
                    )
                }
            }
            Text("${post.authorRank} · ${post.authorTitle}", fontSize = 11.sp, color = OsirisColors.Secondary, maxLines = 1)
        }
        IconButton(onClick = { menu = true }) { Icon(Icons.Outlined.MoreVert, contentDescription = "Post options") }
        DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
            DropdownMenuItem(text = { Text("View profile") }, onClick = {
                menu = false
                actions.onAuthor(post.userId)
            })
            DropdownMenuItem(text = { Text("Share") }, onClick = {
                menu = false
                actions.onShare(post.id)
            })
            if (!isMine) {
                DropdownMenuItem(text = { Text("Report post") }, onClick = {
                    menu = false
                    actions.onReport(post.id)
                })
                DropdownMenuItem(text = { Text("Block ${post.authorName}", color = OsirisColors.Error) }, onClick = {
                    menu = false
                    actions.onBlock(post)
                })
            }
            val delete = actions.onDelete
            if (isMine && delete != null) {
                DropdownMenuItem(text = { Text("Delete post", color = OsirisColors.Error) }, onClick = {
                    menu = false
                    delete(post.id)
                })
            }
        }
    }
}

/** The photo, then the attached workouts and the chart. A caption-only post shows a stat banner. */
@Composable
fun PostMedia(post: FeedPost, baseUrl: String) {
    Column(Modifier.fillMaxWidth()) {
        post.photoUrl?.let { path -> PostPhoto(mediaUrl(baseUrl, path)) }
        if (post.attachments.isNotEmpty() || post.chart != null) {
            Column(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                post.attachments.forEach { WorkoutTiles(it) }
                post.chart?.let { ChartBars(it) }
            }
        } else if (post.photoUrl == null) {
            post.summary.measureLabel?.takeIf { it.isNotBlank() && post.kind != "custom" }?.let { label ->
                Row(
                    Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp)
                        .background(OsirisColors.Primary.copy(alpha = 0.12f), RoundedCornerShape(12.dp)).padding(12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Icon(Icons.Outlined.Verified, null, tint = OsirisColors.Secondary, modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(8.dp))
                    Text(label, fontWeight = FontWeight.Bold)
                }
            }
        }
    }
}

@Composable
private fun PostPhoto(url: String) {
    val image = rememberPostPhoto(url)
    Box(Modifier.fillMaxWidth().aspectRatio(1f).background(OsirisColors.Surface), contentAlignment = Alignment.Center) {
        if (image != null) {
            Image(image, "Post photo", modifier = Modifier.fillMaxWidth().aspectRatio(1f), contentScale = ContentScale.Crop)
        } else {
            Text("Loading photo…", color = OsirisColors.Faint)
        }
    }
}

/** One workout's verified stats: name, PR badge, then up to four tiles. */
@Composable
fun WorkoutTiles(a: PostAttachment) {
    Column(
        Modifier.fillMaxWidth().background(OsirisColors.Background.copy(alpha = 0.55f), RoundedCornerShape(14.dp))
            .padding(12.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Outlined.Verified, null, tint = OsirisColors.Secondary, modifier = Modifier.size(16.dp))
            Spacer(Modifier.width(6.dp))
            Text(a.activityName.ifBlank { a.activityKey }, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
            if (a.isPr) {
                Icon(Icons.Outlined.EmojiEvents, null, tint = OsirisColors.Gold, modifier = Modifier.size(16.dp))
                Text(" PR", color = OsirisColors.Gold, fontWeight = FontWeight.Bold, fontSize = 12.sp)
            }
        }
        Spacer(Modifier.height(8.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            a.tiles.take(MAX_TILES).forEach { t ->
                Column {
                    Text(t.value, fontWeight = FontWeight.ExtraBold, style = MaterialTheme.typography.titleMedium)
                    Text(t.label, fontSize = 11.sp, color = OsirisColors.Faint)
                }
            }
        }
    }
}

/** The weekly-progress chart as bars, the latest week highlighted. */
@Composable
fun ChartBars(chart: PostChart) {
    Column(
        Modifier.fillMaxWidth().background(OsirisColors.Background.copy(alpha = 0.55f), RoundedCornerShape(14.dp)).padding(12.dp),
    ) {
        Text(chart.title, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
        Spacer(Modifier.height(8.dp))
        Row(
            Modifier.fillMaxWidth().height(72.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
            verticalAlignment = Alignment.Bottom,
        ) {
            chart.values.forEachIndexed { i, v ->
                val latest = i == chart.values.lastIndex
                Box(
                    Modifier.weight(1f).fillMaxHeight((v / chart.max).toFloat().coerceIn(MIN_BAR, 1f))
                        .clip(RoundedCornerShape(topStart = 4.dp, topEnd = 4.dp))
                        .background(if (latest) OsirisColors.Primary else OsirisColors.Primary.copy(alpha = 0.35f)),
                )
            }
        }
        Spacer(Modifier.height(4.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(chart.labels.firstOrNull().orEmpty(), fontSize = 10.sp, color = OsirisColors.Faint)
            val last = chart.values.lastOrNull() ?: 0.0
            Text("This week ${last.toInt()} ${chart.unit}", fontSize = 10.sp, color = OsirisColors.Muted)
        }
    }
}

@Composable
private fun PostActions(post: FeedPost, actions: PostCallbacks) {
    val kudos = post.myReaction == "fire"
    Row(Modifier.fillMaxWidth().padding(horizontal = 4.dp), verticalAlignment = Alignment.CenterVertically) {
        IconButton(onClick = { actions.onKudos(post.id) }) {
            Icon(
                if (kudos) Icons.Filled.LocalFireDepartment else Icons.Outlined.LocalFireDepartment,
                contentDescription = if (kudos) "Remove kudos" else "Give kudos",
                tint = if (kudos) OsirisColors.Warning else OsirisColors.Muted,
            )
        }
        IconButton(onClick = { actions.onComments(post.id) }) {
            Icon(Icons.AutoMirrored.Outlined.Comment, contentDescription = "Comments")
        }
        IconButton(onClick = { actions.onShare(post.id) }) { Icon(Icons.Outlined.Share, contentDescription = "Share") }
        Spacer(Modifier.weight(1f))
        if (post.summary.streakDays > 0) {
            Text(
                "🔥 ${post.summary.streakDays}d streak",
                fontSize = 12.sp,
                color = OsirisColors.Muted,
                modifier = Modifier.padding(end = 12.dp),
            )
        }
    }
}

@Composable
private fun PostText(post: FeedPost, actions: PostCallbacks) {
    Column(Modifier.fillMaxWidth().padding(start = 14.dp, end = 14.dp, bottom = 12.dp)) {
        if (post.totalReactions > 0) {
            Text(
                if (post.totalReactions == 1) "1 kudos" else "${post.totalReactions} kudos",
                fontWeight = FontWeight.SemiBold,
                style = MaterialTheme.typography.bodyMedium,
            )
        }
        if (post.caption.isNotBlank()) {
            Text(
                buildAnnotatedString {
                    withStyle(SpanStyle(fontWeight = FontWeight.SemiBold)) { append(post.authorName) }
                    append("  ")
                    append(post.caption)
                },
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.padding(top = 2.dp),
            )
        }
        if (post.commentCount > 0) {
            Text(
                if (post.commentCount == 1) "View 1 comment" else "View all ${post.commentCount} comments",
                color = OsirisColors.Faint,
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.padding(top = 4.dp).clickable { actions.onComments(post.id) },
            )
            post.recentComments.takeLast(2).forEach { c ->
                Text(
                    buildAnnotatedString {
                        withStyle(SpanStyle(fontWeight = FontWeight.SemiBold)) { append(c.authorName) }
                        append("  ")
                        append(c.body)
                    },
                    style = MaterialTheme.typography.bodySmall,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}

/** A square grid tile for Discover and profiles: the photo, else the first workout's headline stat. */
@Composable
fun PostTile(post: FeedPost, baseUrl: String, onClick: () -> Unit) {
    Box(
        Modifier.aspectRatio(1f).background(OsirisColors.Surface).clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        val photo = post.photoUrl?.let { rememberPostPhoto(mediaUrl(baseUrl, it)) }
        val first = post.attachments.firstOrNull()
        when {
            photo != null -> Image(
                photo,
                "Post photo",
                modifier = Modifier.fillMaxWidth().aspectRatio(1f),
                contentScale = ContentScale.Crop,
            )
            first != null -> Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.padding(6.dp)) {
                Text(first.tiles.first().value, fontWeight = FontWeight.ExtraBold, maxLines = 1)
                Text(first.activityName, fontSize = 11.sp, color = OsirisColors.Faint, maxLines = 1)
            }
            post.chart != null -> Text("📈", fontSize = 28.sp)
            else -> Text(post.caption, fontSize = 11.sp, maxLines = 4, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(6.dp))
        }
        if (post.attachments.size > 1) {
            Text(
                "+${post.attachments.size - 1}",
                fontSize = 10.sp,
                modifier = Modifier.align(Alignment.TopEnd).padding(4.dp)
                    .background(OsirisColors.Background.copy(alpha = 0.7f), RoundedCornerShape(6.dp)).padding(horizontal = 4.dp),
            )
        }
    }
}

/** The lock shown on followers-only posts in the composer. */
@Composable
fun FollowersOnlyIcon() = Icon(Icons.Outlined.Lock, contentDescription = null, modifier = Modifier.size(16.dp))

private const val PHOTO_CACHE_ENTRIES = 40
private const val MAX_TILES = 4
private const val MIN_BAR = 0.04f
