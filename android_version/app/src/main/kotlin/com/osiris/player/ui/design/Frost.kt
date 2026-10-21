package com.osiris.player.ui.design

import android.graphics.Bitmap
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageShader
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.graphics.ShaderBrush
import androidx.compose.ui.graphics.TileMode
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawOutline
import androidx.compose.ui.graphics.drawscope.translate
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
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
import kotlin.random.Random

/** The backdrop that frosted surfaces blur. Null outside a [FrostBackground] (previews, dialogs). */
val LocalHazeState = staticCompositionLocalOf<HazeState?> { null }

/** Tiled monochrome grain, generated once per process; 128 px tiles are invisible as a repeat. */
private val grain: ShaderBrush by lazy {
    val side = 128
    val random = Random(7)
    val pixels = IntArray(side * side) { (random.nextInt(256) shl 24) or 0xFFFFFF }
    val bitmap = Bitmap.createBitmap(pixels, side, side, Bitmap.Config.ARGB_8888).asImageBitmap()
    ShaderBrush(ImageShader(bitmap, TileMode.Repeated, TileMode.Repeated))
}

/**
 * The bottom layer of the Z-axis: charcoal slate lit from the top left, with grain over it. The
 * backdrop is the source that [FrostCard] and [FrostBar] blur.
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
                                0f to palette.backgroundAccent.color(),
                                0.55f to palette.background.color(),
                                1f to palette.backgroundAccentAlt.color(),
                                center = Offset.Zero,
                                radius = size.maxDimension * 1.1f,
                            ),
                        )
                        drawRect(grain, alpha = FrostMatte.GRAIN_ALPHA)
                    },
            )
            content()
        }
    }
}

/** HazeStyle for a glass pane. Below Android 12 Haze cannot blur and draws the fallback tint. */
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

/** Specular rim: real glass catches the light at its top edge, so the 1 dp border fades out downwards. */
private fun rim(palette: FrostMatte.Palette): Brush {
    val light = palette.glassBorder.color()
    return Brush.verticalGradient(0f to light, 0.4f to light.copy(alpha = light.alpha * 0.15f), 1f to Color.Transparent)
}

/**
 * Tactile shadow, light from the top left: a hard step, a second half-tone step further out, then
 * a tight contact blur. [pressed] collapses it, so a pane pushes into its shadow when touched.
 */
private fun Modifier.tactileShadow(shape: Shape, palette: FrostMatte.Palette, pressed: Boolean): Modifier = drawBehind {
    val outline = shape.createOutline(size, layoutDirection, this)
    val step = if (pressed) 0.5f else 1f
    val hard = palette.shadow.color()
    translate(FrostMatte.Shadow.STEP2_X.dp.toPx() * step, FrostMatte.Shadow.STEP2_Y.dp.toPx() * step) {
        drawOutline(outline, hard.copy(alpha = FrostMatte.Shadow.STEP2_ALPHA))
    }
    translate(FrostMatte.Shadow.STEP1.dp.toPx() * step, FrostMatte.Shadow.STEP1.dp.toPx() * step) {
        drawOutline(outline, hard)
    }
}

/** A glass pane: tactile shadow, backdrop blur (or opaque [fill]), grain, specular rim. */
fun Modifier.frost(
    haze: HazeState?,
    style: HazeStyle,
    palette: FrostMatte.Palette,
    shape: Shape,
    fill: Color? = null,
    pressed: Boolean = false,
): Modifier =
    this
        .tactileShadow(shape, palette, pressed)
        .clip(shape)
        .then(
            when {
                fill != null -> Modifier.background(fill)
                haze != null -> Modifier.hazeEffect(haze, style)
                else -> Modifier.background(palette.glassFallback.color())
            },
        )
        .drawWithContent {
            drawContent()
            drawRect(grain, alpha = FrostMatte.GRAIN_ALPHA / 2)
        }
        .border(FrostMatte.BORDER_WIDTH.dp, rim(palette), shape)

/**
 * The standard card. Clickable cards are tactile: pressing slides the pane down-right into its
 * shadow. [fill] replaces the glass for a tinted notice; [contentPadding] 0 lets a ListItem pad itself.
 */
@Composable
fun FrostCard(
    modifier: Modifier = Modifier,
    onClick: (() -> Unit)? = null,
    radius: Float = FrostMatte.Radius.MEDIUM,
    contentPadding: Dp = FrostMatte.Spacing.L.dp,
    fill: Color? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    val shape = RoundedCornerShape(radius.dp)
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val shift = if (pressed) (FrostMatte.Shadow.STEP1 / 2).dp else 0.dp
    val clickable = if (onClick != null) {
        Modifier.clickable(interactionSource = interaction, indication = null, role = Role.Button, onClick = onClick)
    } else {
        Modifier
    }
    Column(
        modifier
            .offset(shift, shift)
            .frost(LocalHazeState.current, frostStyle(), FrostTheme.palette, shape, fill, pressed)
            .then(clickable)
            .padding(contentPadding),
    ) {
        // A plain Column provides no content colour, so text would fall back to black on glass.
        CompositionLocalProvider(LocalContentColor provides FrostTheme.palette.textPrimary.color()) { content() }
    }
}

/**
 * The one focal number of a screen: 72 sp, extra bold, tight tracking. [unit] and the labels around
 * it stay small and muted so nothing competes with it.
 */
@Composable
fun HeroMetric(value: String, modifier: Modifier = Modifier, unit: String? = null, label: String? = null, caption: String? = null) {
    val palette = FrostTheme.palette
    Column(modifier.semantics(mergeDescendants = true) {}) {
        if (label != null) Text(label.uppercase(), style = MaterialTheme.typography.labelMedium, color = palette.textMuted.color())
        Row(verticalAlignment = Alignment.Bottom) {
            Text(value, style = MaterialTheme.typography.displayLarge, color = palette.textPrimary.color())
            if (unit != null) {
                Spacer(Modifier.width(8.dp))
                Text(
                    unit,
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                    color = palette.textMuted.color(),
                    modifier = Modifier.padding(bottom = 8.dp),
                )
            }
        }
        if (caption != null) Text(caption, style = MaterialTheme.typography.bodyMedium, color = palette.textSecondary.color())
    }
}

class FrostBarItem(val label: String, val icon: ImageVector, val selected: Boolean, val onClick: () -> Unit)

/**
 * Floating tab bar: a glass slab off the screen edges. The current tab is a chunky accent key with
 * its label; the others are icons only, named for screen readers.
 */
@Composable
fun FrostBar(items: List<FrostBarItem>, modifier: Modifier = Modifier) {
    val palette = FrostTheme.palette
    Row(
        modifier
            .fillMaxWidth()
            .padding(horizontal = FrostMatte.Spacing.L.dp, vertical = FrostMatte.Spacing.S.dp)
            .frost(LocalHazeState.current, frostStyle(), palette, RoundedCornerShape(FrostMatte.Radius.LARGE.dp))
            .height(68.dp)
            .padding(horizontal = FrostMatte.Spacing.S.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        items.forEach { item ->
            val key = RoundedCornerShape(18.dp)
            Row(
                Modifier
                    .then(if (item.selected) Modifier.accentKey(key) else Modifier.clip(key))
                    .selectable(selected = item.selected, role = Role.Tab, onClick = item.onClick)
                    .height(50.dp)
                    .padding(horizontal = if (item.selected) 16.dp else 14.dp)
                    .semantics(mergeDescendants = true) { contentDescription = item.label },
                verticalAlignment = Alignment.CenterVertically,
            ) {
                val tint = if (item.selected) palette.onAccent.color() else palette.textMuted.color()
                Icon(item.icon, contentDescription = null, tint = tint, modifier = Modifier.size(22.dp))
                if (item.selected) {
                    Spacer(Modifier.width(8.dp))
                    Text(item.label, color = tint, style = MaterialTheme.typography.labelLarge)
                }
            }
        }
    }
}

/** An accent fill that sits on its own darker base, like a key: used for the active tab and highlights. */
fun Modifier.accentKey(shape: Shape): Modifier = this
    .drawBehind {
        val outline = shape.createOutline(size, layoutDirection, this)
        translate(0f, 3.dp.toPx()) { drawOutline(outline, Color(FrostMatte.ACCENT_BASE)) }
    }
    .clip(shape)
    .background(Color(FrostMatte.dark.accent))
