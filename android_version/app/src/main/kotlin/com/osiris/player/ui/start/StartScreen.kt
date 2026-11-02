package com.osiris.player.ui.start

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.pager.PagerState
import androidx.compose.foundation.pager.VerticalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowForward
import androidx.compose.material.icons.outlined.AccountBalanceWallet
import androidx.compose.material.icons.outlined.CameraAlt
import androidx.compose.material.icons.outlined.EmojiEvents
import androidx.compose.material.icons.outlined.FitnessCenter
import androidx.compose.material.icons.outlined.Route
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.osiris.player.ui.common.Chip
import com.osiris.player.ui.design.FrostCard
import com.osiris.player.ui.theme.OsirisColors
import kotlin.math.abs
import kotlin.math.sin
import kotlinx.coroutines.launch

private val Ember = Color(0xFFFF6A1A)
private val Gold = Color(0xFFFFC107)
private val Sky = Color(0xFF29B6F6)
private val Violet = Color(0xFFAB47BC)

/** The big entry cards on the Start tab, top to bottom. */
enum class StartCard(
    val title: String,
    val badge: String,
    val caption: String,
    val icon: ImageVector,
    val glow: Color,
) {
    TRAIN(
        "Train",
        "PERSONAL WORKOUT",
        "Your own session. Live heart rate, power, speed and elevation from your watch or phone.",
        Icons.Outlined.FitnessCenter,
        Ember,
    ),
    CHALLENGE(
        "Challenge",
        "COMPETE & CONQUER",
        "Race your connections, official Osiris challenges, and open course targets.",
        Icons.Outlined.EmojiEvents,
        Gold,
    ),
    CAMERA(
        "Camera coach",
        "AI POSE TRACKING",
        "Push-ups, squats, planks and more, counted and verified live on camera.",
        Icons.Outlined.CameraAlt,
        Sky,
    ),
    COURSES(
        "Courses",
        "GPS BENCHMARKS",
        "Run a verified course and set the benchmark time others must beat.",
        Icons.Outlined.Route,
        Violet,
    ),
}

private const val SPIRAL_DEGREES = 36f
private const val SPIRAL_PITCH_DEGREES = 10f
private const val SPIRAL_SWING_DP = 116f
private const val SHRINK = 0.16f
private const val FADE = 0.38f
private const val CAMERA_DISTANCE = 12f
private const val GLOW_ALPHA = 0.45f
private const val BORDER_ALPHA = 0.45f
private const val WALLET_BG_ALPHA = 0.72f
private const val WALLET_BORDER_ALPHA = 0.25f

/**
 * Start: no title, the wallet in the top-right corner, and the entry cards on a spiral. Scrolling
 * turns each card about its vertical and horizontal axes as it swings out to the side, like steps of a helix.
 */
@Composable
fun StartScreen(onOpen: (StartCard) -> Unit, onWallet: (() -> Unit)?) {
    val pager = rememberPagerState { StartCard.entries.size }
    val scope = rememberCoroutineScope()
    Box(Modifier.fillMaxSize()) {
        VerticalPager(
            state = pager,
            contentPadding = PaddingValues(top = 112.dp, bottom = 148.dp),
            pageSpacing = 12.dp,
            modifier = Modifier.fillMaxSize(),
        ) { page ->
            SpiralCard(StartCard.entries[page], pager, page) { onOpen(StartCard.entries[page]) }
        }
        Dots(
            pager = pager,
            onSelect = { page -> scope.launch { pager.animateScrollToPage(page) } },
            modifier = Modifier.align(Alignment.CenterEnd).padding(end = 10.dp),
        )
        if (onWallet != null) {
            IconButton(
                onClick = onWallet,
                modifier = Modifier
                    .align(Alignment.TopEnd)
                    .statusBarsPadding()
                    .padding(top = 8.dp, end = 16.dp)
                    .size(44.dp)
                    .clip(CircleShape)
                    .background(OsirisColors.Surface.copy(alpha = WALLET_BG_ALPHA))
                    .border(1.dp, Color.White.copy(alpha = WALLET_BORDER_ALPHA), CircleShape),
            ) {
                Icon(
                    Icons.Outlined.AccountBalanceWallet,
                    contentDescription = "Wallet",
                    tint = OsirisColors.Primary,
                )
            }
        }
    }
}

@Composable
private fun SpiralCard(card: StartCard, pager: PagerState, page: Int, onClick: () -> Unit) {
    val cardShape = RoundedCornerShape(28.dp)
    FrostCard(
        onClick = onClick,
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 28.dp)
            .fillMaxHeight()
            .graphicsLayer {
                // 0 for the card in focus; ±1 a page away, signed by direction.
                val offset = (pager.currentPage - page) + pager.currentPageOffsetFraction
                val distance = abs(offset).coerceAtMost(1.5f)
                rotationY = offset * SPIRAL_DEGREES
                rotationX = -offset * SPIRAL_PITCH_DEGREES
                translationX = sin(offset) * SPIRAL_SWING_DP.dp.toPx()
                val scale = 1f - SHRINK * distance.coerceAtMost(1f)
                scaleX = scale
                scaleY = scale
                alpha = 1f - FADE * distance
                cameraDistance = CAMERA_DISTANCE * density
            }
            .border(1.dp, card.glow.copy(alpha = BORDER_ALPHA), cardShape)
            .semantics { role = Role.Button },
    ) {
        Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.SpaceBetween) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.Top,
            ) {
                Box(
                    Modifier
                        .size(88.dp)
                        .clip(CircleShape)
                        .background(Brush.radialGradient(listOf(card.glow.copy(alpha = GLOW_ALPHA), Color.Transparent)))
                        .border(1.dp, card.glow.copy(alpha = BORDER_ALPHA), CircleShape),
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(card.icon, contentDescription = null, tint = card.glow, modifier = Modifier.size(44.dp))
                }
                Chip(card.badge, card.glow)
            }
            Column {
                Text(card.title, style = MaterialTheme.typography.displaySmall, fontWeight = FontWeight.Bold)
                Spacer(Modifier.height(8.dp))
                Text(card.caption, style = MaterialTheme.typography.bodyLarge, color = OsirisColors.Muted)
                Spacer(Modifier.height(16.dp))
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(
                        "Open ${card.title}",
                        style = MaterialTheme.typography.labelLarge,
                        color = card.glow,
                        fontWeight = FontWeight.SemiBold,
                    )
                    Icon(
                        Icons.AutoMirrored.Outlined.ArrowForward,
                        contentDescription = null,
                        tint = card.glow,
                        modifier = Modifier.size(18.dp),
                    )
                }
            }
        }
    }
}

@Composable
private fun Dots(pager: PagerState, onSelect: (Int) -> Unit, modifier: Modifier) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(8.dp)) {
        repeat(pager.pageCount) { i ->
            val on = i == pager.currentPage
            val accent = StartCard.entries[i].glow
            Box(
                Modifier
                    .size(width = 7.dp, height = if (on) 22.dp else 7.dp)
                    .clip(RoundedCornerShape(4.dp))
                    .background(if (on) accent else OsirisColors.Faint)
                    .clickable { onSelect(i) },
            )
        }
    }
}
