package com.osiris.player.ui.start

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.path
import androidx.compose.ui.unit.dp

/**
 * The Start tab's mark, "ignition": a ring broken at the top like a power symbol, its key stroke in
 * the gap, and a forward chevron inside. The bar tints it, so the colours here are placeholders.
 */
val StartIcon: ImageVector = ImageVector.Builder("Start", 24.dp, 24.dp, 24f, 24f).apply {
    // Ring from 1 o'clock clockwise round to 11 o'clock, radius 9 about (12, 12).
    path(stroke = SolidColor(Color.Black), strokeLineWidth = 2f, strokeLineCap = StrokeCap.Round) {
        moveTo(16.5f, 4.2f)
        arcTo(9f, 9f, 0f, isMoreThanHalf = true, isPositiveArc = true, x1 = 7.5f, y1 = 4.2f)
    }
    path(stroke = SolidColor(Color.Black), strokeLineWidth = 2f, strokeLineCap = StrokeCap.Round) {
        moveTo(12f, 1.8f)
        lineTo(12f, 6.2f)
    }
    path(fill = SolidColor(Color.Black)) {
        moveTo(10f, 9f)
        lineTo(16f, 12.5f)
        lineTo(10f, 16f)
        close()
    }
}.build()
