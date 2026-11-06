package com.osiris.player.ui.design

import android.graphics.RenderEffect
import android.graphics.RuntimeShader
import android.os.Build
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.Spring
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.animation.shrinkVertically
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
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.progressSemantics
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowForward
import androidx.compose.material3.Icon
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.LocalTextStyle
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.drawWithCache
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.BlendMode
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.CompositingStrategy
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.asComposeRenderEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.graphics.drawscope.translate
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.layer.GraphicsLayer
import androidx.compose.ui.graphics.layer.drawLayer
import androidx.compose.ui.graphics.rememberGraphicsLayer
import androidx.compose.ui.layout.layout
import androidx.compose.ui.layout.onPlaced
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.positionInRoot
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.osiris.player.ui.theme.FrostTheme
import com.osiris.player.ui.theme.color
import com.osiris.shared.core.design.FrostMatte
import com.osiris.shared.core.design.FrostMatte.Depth
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin

/** The matte charcoal floor behind every screen. */
@Composable
fun FrostBackground(modifier: Modifier = Modifier, content: @Composable BoxScope.() -> Unit) {
    val palette = FrostTheme.palette
    Box(
        modifier
            .fillMaxSize()
            .background(Brush.verticalGradient(listOf(palette.background.color(), palette.backgroundAccentAlt.color()))),
        content = content,
    )
}

/** A card surface: flat slate with a subtle 1 dp border. [fill] tints it for a notice or a selected item. */
fun Modifier.frost(palette: FrostMatte.Palette, shape: Shape, fill: Color? = null): Modifier =
    this
        .clip(shape)
        .background(palette.glassFallback.color())
        .then(if (fill != null) Modifier.background(fill) else Modifier)
        .border(FrostMatte.BORDER_WIDTH.dp, palette.glassBorder.color(), shape)

/** Lets a carousel run [by] past its parent's padding to the screen edges, so cards scroll off the screen, not off the margin. */
fun Modifier.bleed(by: Dp): Modifier = layout { measurable, constraints ->
    val extra = by.roundToPx()
    val width = constraints.maxWidth + extra * 2
    val placeable = measurable.measure(constraints.copy(minWidth = width, maxWidth = width))
    layout(constraints.maxWidth, placeable.height) { placeable.place(-extra, 0) }
}

/** Fades a scrolling list out at its top instead of cutting it off against the top bar. */
fun Modifier.softEdges(fade: Dp = 24.dp): Modifier = this
    .graphicsLayer { compositingStrategy = CompositingStrategy.Offscreen }
    .drawWithContent {
        drawContent()
        val share = (fade.toPx() / size.height.coerceAtLeast(1f)).coerceAtMost(0.5f)
        drawRect(
            Brush.verticalGradient(0f to Color.Transparent, share to Color.Black),
            blendMode = BlendMode.DstIn,
        )
    }

/** A recess in a card, for inputs, tracks and summaries: the floor colour showing through. */
fun Modifier.well(shape: Shape): Modifier = clip(shape).background(Color(FrostMatte.WELL))

/** An icon on a small round badge. Decorative: name the thing in the text beside it. */
@Composable
fun IconOrb(icon: ImageVector, modifier: Modifier = Modifier, tint: Color = FrostTheme.palette.accent.color(), size: Dp = 44.dp) {
    Box(
        modifier
            .size(size)
            .clip(CircleShape)
            .background(FrostTheme.palette.glassBorder.color()),
        contentAlignment = Alignment.Center,
    ) {
        Icon(icon, contentDescription = null, tint = tint, modifier = Modifier.size(size / 2))
    }
}

/** Scale for a pressed control: a spring, so it gives under the finger and settles back. */
@Composable
private fun pressScale(pressed: Boolean, to: Float) =
    animateFloatAsState(if (pressed) to else 1f, spring(dampingRatio = 0.6f, stiffness = Spring.StiffnessMedium), label = "press")

/**
 * The standard card. Clickable cards shrink slightly under the finger. [fill] tints it for a notice;
 * [contentPadding] 0 lets a ListItem pad itself.
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
    val scale by pressScale(pressed, 0.98f)
    val clickable = if (onClick != null) {
        Modifier.clickable(interactionSource = interaction, indication = null, role = Role.Button, onClick = onClick)
    } else {
        Modifier
    }
    Column(
        modifier
            .graphicsLayer {
                scaleX = scale
                scaleY = scale
            }
            .frost(FrostTheme.palette, shape, fill)
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
        if (label != null) Text(label, style = MaterialTheme.typography.labelMedium, color = palette.textMuted.color())
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

/** Width of the [EnergyRing] groove, in dp. */
private const val RING_WIDTH = 16f

/**
 * Live progress as a groove in the card, filled with powder blue, with an orange spark on its
 * leading edge. With no progress yet the spark waits at the top, ready to go.
 */
@Composable
fun EnergyRing(progress: Float, modifier: Modifier = Modifier, content: @Composable BoxScope.() -> Unit) {
    val palette = FrostTheme.palette
    val fill = palette.accentAlt.color()
    val spark = palette.energy.color()
    val clamped = progress.coerceIn(0f, 1f)
    val swept by animateFloatAsState(clamped, spring(stiffness = Spring.StiffnessVeryLow), label = "ring")
    Box(
        modifier
            .aspectRatio(1f)
            .progressSemantics(clamped)
            .drawBehind {
                val width = RING_WIDTH.dp.toPx()
                val radius = (size.minDimension - width) / 2 - width
                drawCircle(Color(FrostMatte.WELL), radius, style = Stroke(width))
                if (swept > 0f) {
                    rotate(-90f) {
                        drawArc(
                            fill,
                            startAngle = 0f,
                            sweepAngle = 360f * swept,
                            useCenter = false,
                            topLeft = center - Offset(radius, radius),
                            size = Size(radius * 2, radius * 2),
                            style = Stroke(width * 0.72f, cap = StrokeCap.Round),
                        )
                    }
                }
                val angle = 2 * PI * (swept - 0.25f)
                val tip = center + Offset(cos(angle).toFloat(), sin(angle).toFloat()) * radius
                drawCircle(spark, width * 0.6f, tip)
            },
        contentAlignment = Alignment.Center,
        content = content,
    )
}

/** How much space the tab bar takes above the system navigation bar. */
val TabBarHeight = 84.dp

/**
 * How far the tab bar reaches up from the bottom of a tab's screen; 0 on screens without it. Those
 * screens run full height behind the bar, so their scrolling content pads its end by this much.
 */
val LocalTabBarInset = compositionLocalOf { 0.dp }

/**
 * Liquid glass, with no blur: the bar stays sharp through its middle and bends inwards towards its rim,
 * splitting slightly into colour there, under a thin specular edge.
 */
private const val LIQUID_GLASS = """
uniform shader content;
uniform float2 size;
uniform float dp;

float capsule(float2 p) {
    float radius = size.y * 0.5;
    float2 q = abs(p) - size * 0.5 + radius;
    return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - radius;
}

half4 main(float2 at) {
    float2 p = at - size * 0.5;
    float d = capsule(p);
    float2 e = float2(1.0, 0.0);
    float2 slope = float2(capsule(p + e.xy) - capsule(p - e.xy), capsule(p + e.yx) - capsule(p - e.yx));
    float2 normal = normalize(slope + 0.0001);
    float bezel = clamp(1.0 + d / (size.y * 0.42), 0.0, 1.0);
    float2 bend = normal * bezel * bezel * bezel * size.y * 0.45;
    half4 red = content.eval(at - bend * 0.96);
    half4 green = content.eval(at - bend);
    half4 blue = content.eval(at - bend * 1.04);
    float rim = 1.0 - smoothstep(0.0, 1.5 * dp, -d);
    float lit = clamp(dot(normal, float2(-0.35, -0.94)), 0.0, 1.0);
    float bounce = clamp(dot(normal, float2(0.35, 0.94)), 0.0, 1.0);
    float light = rim * (0.2 + 0.65 * lit + 0.3 * bounce) + bezel * bezel * 0.05;
    half3 color = half3(red.r, green.g, blue.b) + light;
    return half4(color, min(green.a + light, 1.0));
}
"""

class FrostBarItem(val label: String, val icon: ImageVector, val selected: Boolean, val onClick: () -> Unit)

/** How the highlight travels between tabs: settling with a little overshoot. */
private val highlightSpring = spring<Float>(dampingRatio = 0.68f, stiffness = Spring.StiffnessLow)

/**
 * Floating tab bar: a capsule of liquid glass over [backdrop], the screen behind it. Every tab holds
 * the same width. The current one shows its icon in orange above its name, on a plain highlight that
 * slides from tab to tab; the others are white icons, named for screen readers.
 */
@Composable
fun FrostBar(items: List<FrostBarItem>, backdrop: GraphicsLayer, modifier: Modifier = Modifier) {
    val palette = FrostTheme.palette
    val glass = RoundedCornerShape(FrostMatte.Radius.PILL.dp)
    val fallback = palette.background.color().copy(alpha = 0.85f)
    val lens = rememberGraphicsLayer()
    var origin by remember { mutableStateOf(Offset.Zero) }
    val selected = items.indexOfFirst { it.selected }.coerceAtLeast(0)
    val highlight = remember { Animatable(selected.toFloat()) }
    LaunchedEffect(selected) { highlight.animateTo(selected.toFloat(), highlightSpring) }
    Box(
        modifier
            .fillMaxWidth()
            .padding(horizontal = FrostMatte.Spacing.XXL.dp, vertical = FrostMatte.Spacing.S.dp)
            .clip(glass)
            .onPlaced { origin = it.positionInRoot() }
            .drawWithCache {
                // Below Android 13, which cannot run the shader, the bar is a dark translucent fill.
                val glassy = Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                    val shader = RuntimeShader(LIQUID_GLASS)
                    shader.setFloatUniform("size", size.width, size.height)
                    shader.setFloatUniform("dp", density)
                    lens.renderEffect = RenderEffect.createRuntimeShaderEffect(shader, "content").asComposeRenderEffect()
                }
                val inset = FrostMatte.Spacing.S.dp.toPx()
                val slot = (size.width - inset * 2) / items.size
                val pill = Size(slot - 6.dp.toPx(), 56.dp.toPx())
                // Read in the draw phase, so the slide redraws the bar without recomposing it.
                onDrawWithContent {
                    if (glassy) {
                        lens.record {
                            translate(-origin.x, -origin.y) { drawLayer(backdrop) }
                            // Slightly darker than the screen behind it, so the icons stay readable over bright content.
                            drawRect(Color.Black.copy(alpha = 0.14f))
                        }
                        drawLayer(lens)
                    } else {
                        drawRect(fallback)
                    }
                    drawRoundRect(
                        Color.White.copy(alpha = 0.12f),
                        topLeft = Offset(inset + slot * (highlight.value + 0.5f) - pill.width / 2, (size.height - pill.height) / 2),
                        size = pill,
                        cornerRadius = CornerRadius(pill.height / 2),
                    )
                    drawContent()
                }
            }
            .height(68.dp)
            .padding(horizontal = FrostMatte.Spacing.S.dp),
        contentAlignment = Alignment.CenterStart,
    ) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            items.forEach { item ->
                val tint by animateColorAsState(
                    if (item.selected) palette.accent.color() else palette.textPrimary.color(),
                    label = "tab tint",
                )
                Column(
                    Modifier
                        .weight(1f)
                        .height(56.dp)
                        .clip(glass)
                        .selectable(selected = item.selected, role = Role.Tab, onClick = item.onClick)
                        .semantics(mergeDescendants = true) { contentDescription = item.label },
                    verticalArrangement = Arrangement.Center,
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Icon(item.icon, contentDescription = null, tint = tint, modifier = Modifier.size(22.dp))
                    AnimatedVisibility(item.selected, enter = fadeIn() + expandVertically(), exit = fadeOut() + shrinkVertically()) {
                        Text(
                            item.label,
                            color = tint,
                            style = MaterialTheme.typography.labelMedium,
                            maxLines = 1,
                            modifier = Modifier.padding(top = 2.dp),
                        )
                    }
                }
            }
        }
    }
}

/** A solid orange face: the active tab and the player's own row. */
fun Modifier.accentKey(shape: Shape): Modifier = clip(shape).background(Color(FrostMatte.dark.accent))

/**
 * A fully rounded button: solid orange with a trailing arrow when [primary], otherwise a powder blue
 * outline with matching text. Pressing shrinks it under the finger, then it springs back.
 */
@Composable
private fun Key(onClick: () -> Unit, modifier: Modifier, enabled: Boolean, primary: Boolean, content: @Composable RowScope.() -> Unit) {
    val palette = FrostTheme.palette
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val scale by pressScale(pressed && enabled, Depth.PRESS_SCALE)
    val shape = RoundedCornerShape(FrostMatte.Radius.PILL.dp)
    val face = if (primary) Modifier.accentKey(shape) else Modifier.clip(shape).border(1.5.dp, palette.accentAlt.color(), shape)
    Row(
        modifier
            .defaultMinSize(minHeight = FrostMatte.MIN_TOUCH_TARGET.dp)
            .graphicsLayer {
                scaleX = scale
                scaleY = scale
                alpha = if (enabled) 1f else 0.4f
            }
            .then(face)
            .clickable(interactionSource = interaction, indication = null, enabled = enabled, role = Role.Button, onClick = onClick)
            .padding(horizontal = 22.dp, vertical = 4.dp),
        horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        val ink = if (primary) palette.onAccent.color() else palette.accentAlt.color()
        CompositionLocalProvider(LocalContentColor provides ink, LocalTextStyle provides MaterialTheme.typography.labelLarge) {
            content()
            if (primary) {
                Spacer(Modifier.width(8.dp))
                Icon(Icons.AutoMirrored.Filled.ArrowForward, contentDescription = null, modifier = Modifier.size(18.dp))
            }
        }
    }
}

/** A screen's main action. */
@Composable
fun KeyButton(onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true, content: @Composable RowScope.() -> Unit) =
    Key(onClick, modifier, enabled, primary = true, content)

/** A secondary action. */
@Composable
fun RaisedButton(onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true, content: @Composable RowScope.() -> Unit) =
    Key(onClick, modifier, enabled, primary = false, content)

/** A floating, pill-shaped HUD readout, used for messages instead of a flat snackbar. */
@Composable
fun HudPill(text: String, modifier: Modifier = Modifier) {
    val palette = FrostTheme.palette
    val pill = RoundedCornerShape(FrostMatte.Radius.PILL.dp)
    Box(modifier.fillMaxWidth().padding(horizontal = 24.dp, vertical = 12.dp), contentAlignment = Alignment.Center) {
        Text(
            text,
            style = MaterialTheme.typography.titleSmall,
            color = palette.textPrimary.color(),
            modifier = Modifier
                .frost(palette, pill)
                .padding(horizontal = 20.dp, vertical = 12.dp),
        )
    }
}
