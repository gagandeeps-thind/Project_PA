package com.osiris.player.ui.start

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Spacer
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
import androidx.compose.ui.unit.dp
import com.osiris.player.ui.design.FrostCard
import com.osiris.player.ui.theme.OsirisColors
import kotlin.math.abs
import kotlin.math.sin

private val Ember = Color(0xFFFF6A1A)
private val Gold = Color(0xFFFFC107)
private val Sky = Color(0xFF29B6F6)
private val Violet = Color(0xFFAB47BC)

/** The big entry cards on the Start tab, top to bottom. */
enum class StartCard(val title: String, val caption: String, val icon: ImageVector, val glow: Color) {
    TRAIN("Train", "Your own session. Live heart rate, power, speed and elevation from your watch.", Icons.Outlined.FitnessCenter, Ember),
    CHALLENGE("Challenge", "Race your connections and Osiris challenges. Every session counts.", Icons.Outlined.EmojiEvents, Gold),
    CAMERA("Camera coach", "Push-ups, squats, planks and more, counted on camera.", Icons.Outlined.CameraAlt, Sky),
    COURSES("Courses", "Run a course and set the time others must beat.", Icons.Outlined.Route, Violet),
}

private const val SPIRAL_DEGREES = 35f
private const val SPIRAL_SWING_DP = 120f
private const val SHRINK = 0.15f
private const val FADE = 0.4f
private const val CAMERA_DISTANCE = 12f
private const val GLOW_ALPHA = 0.45f

/**
 * Start: no title, the wallet in the top-right corner, and the entry cards on a spiral. Scrolling
 * turns each card about its vertical axis as it swings out to the side, like steps of a helix.
 */
@Composable
fun StartScreen(onOpen: (StartCard) -> Unit, onWallet: (() -> Unit)?) {
    val pager = rememberPagerState { StartCard.entries.size }
    Box(Modifier.fillMaxSize()) {
        VerticalPager(
            state = pager,
            contentPadding = PaddingValues(vertical = 150.dp),
            pageSpacing = 8.dp,
            modifier = Modifier.fillMaxSize(),
        ) { page ->
            SpiralCard(StartCard.entries[page], pager, page) { onOpen(StartCard.entries[page]) }
        }
        Dots(pager, Modifier.align(Alignment.CenterEnd).padding(end = 10.dp))
        if (onWallet != null) {
            IconButton(onClick = onWallet, modifier = Modifier.align(Alignment.TopEnd).statusBarsPadding().padding(8.dp)) {
                Icon(Icons.Outlined.AccountBalanceWallet, contentDescription = "Wallet")
            }
        }
    }
}

@Composable
private fun SpiralCard(card: StartCard, pager: PagerState, page: Int, onClick: () -> Unit) {
    FrostCard(
        onClick = onClick,
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 32.dp)
            .height(340.dp)
            .graphicsLayer {
                // 0 for the card in focus; ±1 a page away, signed by direction.
                val offset = (pager.currentPage - page) + pager.currentPageOffsetFraction
                val distance = abs(offset).coerceAtMost(1.5f)
                rotationY = offset * SPIRAL_DEGREES
                translationX = sin(offset) * SPIRAL_SWING_DP.dp.toPx()
                val scale = 1f - SHRINK * distance.coerceAtMost(1f)
                scaleX = scale
                scaleY = scale
                alpha = 1f - FADE * distance
                cameraDistance = CAMERA_DISTANCE * density
            }
            .semantics { role = Role.Button },
    ) {
        Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.SpaceBetween) {
            Box(
                Modifier
                    .size(88.dp)
                    .clip(CircleShape)
                    .background(Brush.radialGradient(listOf(card.glow.copy(alpha = GLOW_ALPHA), Color.Transparent))),
                contentAlignment = Alignment.Center,
            ) {
                Icon(card.icon, contentDescription = null, tint = card.glow, modifier = Modifier.size(44.dp))
            }
            Column {
                Text(card.title, style = MaterialTheme.typography.displaySmall)
                Spacer(Modifier.height(8.dp))
                Text(card.caption, style = MaterialTheme.typography.bodyLarge, color = OsirisColors.Muted)
            }
        }
    }
}

@Composable
private fun Dots(pager: PagerState, modifier: Modifier) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        repeat(pager.pageCount) { i ->
            val on = i == pager.currentPage
            Box(
                Modifier
                    .size(width = 6.dp, height = if (on) 18.dp else 6.dp)
                    .clip(RoundedCornerShape(3.dp))
                    .background(if (on) OsirisColors.Primary else OsirisColors.Faint),
            )
        }
    }
}
