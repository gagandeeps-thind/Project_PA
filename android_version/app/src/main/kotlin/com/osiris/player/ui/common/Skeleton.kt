package com.osiris.player.ui.common

import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.osiris.player.ui.theme.OsirisColors

/**
 * Placeholder cards in the shape of a list while it loads, so the screen keeps its layout
 * instead of jumping from a centred spinner to content. The pulse runs in the draw phase
 * (graphicsLayer alpha), so it never recomposes the placeholders.
 */
@Composable
fun LoadingSkeleton(modifier: Modifier = Modifier, rows: Int = 5) {
    val pulse = rememberInfiniteTransition(label = "skeleton")
    val alpha by pulse.animateFloat(
        initialValue = 0.35f,
        targetValue = 0.8f,
        animationSpec = infiniteRepeatable(tween(durationMillis = 800), RepeatMode.Reverse),
        label = "skeletonAlpha",
    )
    Column(
        modifier.fillMaxSize().padding(16.dp).semantics { contentDescription = "Loading" },
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        repeat(rows) { i ->
            Box(
                Modifier
                    .fillMaxWidth(if (i % 2 == 0) 1f else 0.85f)
                    .height(if (i == 0) 120.dp else 72.dp)
                    .graphicsLayer { this.alpha = alpha }
                    .background(OsirisColors.Surface, RoundedCornerShape(16.dp)),
            )
        }
    }
}
