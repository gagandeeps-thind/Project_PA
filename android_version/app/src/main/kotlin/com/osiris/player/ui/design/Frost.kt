package com.osiris.player.ui.design

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.osiris.player.ui.theme.FrostTheme
import com.osiris.player.ui.theme.color
import com.osiris.shared.core.design.FrostMatte
import dev.chrisbanes.haze.HazeState
import dev.chrisbanes.haze.HazeStyle
import dev.chrisbanes.haze.HazeTint
import dev.chrisbanes.haze.hazeEffect
import dev.chrisbanes.haze.hazeSource
import dev.chrisbanes.haze.rememberHazeState

/** The backdrop that frosted surfaces blur. Null outside a [FrostBackground] (previews, dialogs). */
val LocalHazeState = staticCompositionLocalOf<HazeState?> { null }

/**
 * Matte backdrop: the palette background with two soft, low-contrast accent fields and no gloss.
 * The backdrop is the source that [FrostCard] and [FrostBar] blur.
 */
@Composable
fun FrostBackground(modifier: Modifier = Modifier, content: @Composable BoxScope.() -> Unit) {
    val palette = FrostTheme.palette
    val haze = rememberHazeState()
    CompositionLocalProvider(LocalHazeState provides haze) {
        Box(modifier.fillMaxSize()) {
            Box(
                Modifier
                    .fillMaxSize()
                    .hazeSource(haze)
                    .background(palette.background.color())
                    .drawBehind {
                        drawRect(
                            Brush.radialGradient(
                                listOf(palette.backgroundAccent.color(), Color.Transparent),
                                center = Offset(size.width * 0.1f, size.height * 0.05f),
                                radius = size.maxDimension * 0.7f,
                            ),
                        )
                        drawRect(
                            Brush.radialGradient(
                                listOf(palette.backgroundAccentAlt.color(), Color.Transparent),
                                center = Offset(size.width * 0.95f, size.height * 0.85f),
                                radius = size.maxDimension * 0.6f,
                            ),
                        )
                    },
            )
            content()
        }
    }
}

/** HazeStyle for a FrostMatte glass surface. Below Android 12 Haze cannot blur and draws the fallback tint. */
@Composable
fun frostStyle(): HazeStyle {
    val palette = FrostTheme.palette
    return HazeStyle(
        backgroundColor = palette.background.color(),
        tint = HazeTint(palette.glassFill.color()),
        blurRadius = FrostMatte.BLUR_RADIUS.dp,
        noiseFactor = FrostMatte.GRAIN_ALPHA,
        fallbackTint = HazeTint(palette.glassFallback.color()),
    )
}

/** A frosted glass surface: backdrop blur, translucent fill, 1 dp hairline, soft diffuse shadow. */
fun Modifier.frost(
    haze: HazeState?,
    style: HazeStyle,
    palette: FrostMatte.Palette,
    shape: Shape,
    elevation: Dp = (FrostMatte.Shadow.RADIUS / 3).dp,
): Modifier =
    this
        .shadow(elevation, shape, clip = false, ambientColor = palette.shadow.color(), spotColor = palette.shadow.color())
        .clip(shape)
        .then(if (haze != null) Modifier.hazeEffect(haze, style) else Modifier.background(palette.glassFallback.color()))
        .border(FrostMatte.BORDER_WIDTH.dp, palette.glassBorder.color(), shape)

@Composable
fun FrostCard(
    modifier: Modifier = Modifier,
    onClick: (() -> Unit)? = null,
    radius: Float = FrostMatte.Radius.MEDIUM,
    contentPadding: Dp = FrostMatte.Spacing.L.dp,
    content: @Composable ColumnScope.() -> Unit,
) {
    val shape = RoundedCornerShape(radius.dp)
    val clickable = if (onClick != null) Modifier.clickable(role = Role.Button, onClick = onClick) else Modifier
    Column(
        modifier
            .frost(LocalHazeState.current, frostStyle(), FrostTheme.palette, shape)
            .then(clickable)
            .padding(contentPadding),
        content = content,
    )
}

class FrostBarItem(val label: String, val icon: ImageVector, val selected: Boolean, val onClick: () -> Unit)

/** Floating frosted tab bar. */
@Composable
fun FrostBar(items: List<FrostBarItem>, modifier: Modifier = Modifier) {
    val palette = FrostTheme.palette
    Row(
        modifier
            .padding(horizontal = FrostMatte.Spacing.L.dp, vertical = FrostMatte.Spacing.S.dp)
            .frost(LocalHazeState.current, frostStyle(), palette, RoundedCornerShape(FrostMatte.Radius.LARGE.dp))
            .padding(horizontal = FrostMatte.Spacing.S.dp),
        horizontalArrangement = Arrangement.SpaceEvenly,
    ) {
        items.forEach { item ->
            val tint = if (item.selected) palette.accent.color() else palette.textMuted.color()
            Column(
                Modifier
                    .weight(1f)
                    .defaultMinSize(minHeight = FrostMatte.MIN_TOUCH_TARGET.dp)
                    .clip(RoundedCornerShape(FrostMatte.Radius.SMALL.dp))
                    .selectable(selected = item.selected, role = Role.Tab, onClick = item.onClick)
                    .padding(vertical = FrostMatte.Spacing.S.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center,
            ) {
                Icon(item.icon, contentDescription = null, tint = tint)
                Text(item.label, color = tint, style = MaterialTheme.typography.labelMedium)
            }
        }
    }
}
