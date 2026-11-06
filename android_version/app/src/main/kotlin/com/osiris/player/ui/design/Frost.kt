package com.osiris.player.ui.design

import android.graphics.Bitmap
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.hardware.display.DisplayManager
import android.provider.Settings
import android.view.Display
import android.view.Surface
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.Spring
import androidx.compose.animation.expandHorizontally
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkHorizontally
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.foundation.background
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
import androidx.compose.material3.Icon
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.LocalTextStyle
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.State
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.draw.dropShadow
import androidx.compose.ui.draw.innerShadow
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.BlendMode
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.CompositingStrategy
import androidx.compose.ui.graphics.ImageShader
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.graphics.ShaderBrush
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.TileMode
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawOutline
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.layout
import androidx.compose.ui.layout.onPlaced
import androidx.compose.ui.layout.positionInParent
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Constraints
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.LifecycleResumeEffect
import com.osiris.player.ui.theme.FrostTheme
import com.osiris.player.ui.theme.color
import com.osiris.shared.core.design.FrostMatte
import com.osiris.shared.core.design.FrostMatte.Depth
import kotlinx.coroutines.launch
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.min
import kotlin.math.roundToInt
import kotlin.math.sin
import kotlin.random.Random

private val lightAtRest: State<FrostMatte.Fall> = mutableStateOf(Depth.REST)

/**
 * Where shadows fall, from the phone's tilt. A [State] read only while drawing, so tilting redraws
 * shadows and rims without recomposing a screen.
 */
val LocalLight = staticCompositionLocalOf { lightAtRest }

/** Tiled monochrome grain, generated once per process; 128 px tiles are invisible as a repeat. */
private val grain: ShaderBrush by lazy {
    val side = 128
    val random = Random(7)
    val pixels = IntArray(side * side) { (random.nextInt(256) shl 24) or 0xFFFFFF }
    val bitmap = Bitmap.createBitmap(pixels, side, side, Bitmap.Config.ARGB_8888).asImageBitmap()
    ShaderBrush(ImageShader(bitmap, TileMode.Repeated, TileMode.Repeated))
}

/** Low-pass weight per gravity sample, and the smallest change worth a redraw. */
private const val SMOOTHING = 0.12f
private const val DEADBAND = 0.004f

/**
 * The light, fixed in the world: gravity tells which way is down, and shadows fall that way. Only
 * listens while the app is in front, and stays at rest when the system has animations turned off.
 */
@Composable
private fun rememberLight(): State<FrostMatte.Fall> {
    val context = LocalContext.current
    val light = remember { mutableStateOf(Depth.REST) }
    LifecycleResumeEffect(context) {
        val sensors = context.getSystemService(SensorManager::class.java)
        val sensor = sensors?.getDefaultSensor(Sensor.TYPE_GRAVITY) ?: sensors?.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
        val still = Settings.Global.getFloat(context.contentResolver, Settings.Global.ANIMATOR_DURATION_SCALE, 1f) == 0f
        val display = context.getSystemService(DisplayManager::class.java)?.getDisplay(Display.DEFAULT_DISPLAY)
        val rotation = { display?.rotation ?: Surface.ROTATION_0 }
        if (sensors == null || sensor == null || still) {
            light.value = Depth.REST
            return@LifecycleResumeEffect onPauseOrDispose {}
        }
        val listener = object : SensorEventListener {
            override fun onSensorChanged(event: SensorEvent) {
                // Gravity sensors report world-up in the device's portrait axes (y up); shadows want
                // world-down in the screen's axes (y down), which turn with the display.
                val (ux, uy) = event.values[0] / SensorManager.GRAVITY_EARTH to event.values[1] / SensorManager.GRAVITY_EARTH
                val target = when (rotation()) {
                    Surface.ROTATION_90 -> Depth.fall(uy, ux)
                    Surface.ROTATION_180 -> Depth.fall(ux, -uy)
                    Surface.ROTATION_270 -> Depth.fall(-uy, -ux)
                    else -> Depth.fall(-ux, uy)
                }
                val now = light.value
                val x = now.x + (target.x - now.x) * SMOOTHING
                val y = now.y + (target.y - now.y) * SMOOTHING
                if (abs(x - now.x) + abs(y - now.y) > DEADBAND) light.value = FrostMatte.Fall(x, y)
            }

            override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) = Unit
        }
        sensors.registerListener(listener, sensor, SensorManager.SENSOR_DELAY_GAME)
        onPauseOrDispose { sensors.unregisterListener(listener) }
    }
    return light
}

/**
 * The floor of the Z-axis: pitch black with nothing on it, so every pane reads as floating. It owns
 * the [LocalLight] every pane casts by. There is no backdrop blur: blurring black is black, and
 * skipping it keeps long lists scrolling at full frame rate.
 */
@Composable
fun FrostBackground(modifier: Modifier = Modifier, content: @Composable BoxScope.() -> Unit) {
    CompositionLocalProvider(LocalLight provides rememberLight()) {
        Box(modifier.fillMaxSize().background(FrostTheme.palette.background.color()), content = content)
    }
}

/**
 * The shadow a pane [height] points above the floor casts: a soft ambient shadow that falls with the
 * light, a faint highlight on the opposite side so it reads as raised (neumorphism on black), a tight
 * contact shadow at its edge and, for floating chrome, a crisp [ring] around it.
 */
fun Modifier.depth(shape: Shape, height: Float, shadow: Color, light: State<FrostMatte.Fall>, ring: Boolean = false): Modifier =
    this
        .dropShadow(shape) {
            val fall = light.value
            val reach = height.dp.toPx() * 0.6f
            radius = reach * Depth.AMBIENT_BLUR_PER_HEIGHT
            offset = -Offset(fall.x * reach, fall.y * reach)
            color = Color.White
            alpha = 0.07f
        }
        .dropShadow(shape) {
            val fall = light.value
            val reach = height.dp.toPx()
            radius = reach * Depth.AMBIENT_BLUR_PER_HEIGHT
            offset = Offset(fall.x * reach, fall.y * reach)
            color = shadow
            alpha = Depth.AMBIENT_ALPHA
        }
        .dropShadow(shape) {
            val fall = light.value
            val reach = height.dp.toPx() * Depth.CONTACT_SHARE
            radius = Depth.CONTACT_BLUR.dp.toPx()
            offset = Offset(fall.x * reach, fall.y * reach)
            color = shadow
            alpha = Depth.CONTACT_ALPHA
        }
        .then(
            if (ring) {
                Modifier.dropShadow(shape) {
                    spread = 1.dp.toPx()
                    color = shadow
                }
            } else {
                Modifier
            },
        )

/** The faint aqua of a rim all the way round; the bright edge facing the light is drawn over it. */
private val BEZEL = Color(0x38A1F7F5)

/**
 * Icy rim: a faint aqua ring all round, bright on the edge facing the light and fading on the far
 * edge. Drawn inside the clip, so each stroke is twice its visible width.
 */
private fun Modifier.rim(shape: Shape, rim: Color, light: State<FrostMatte.Fall>): Modifier = drawWithContent {
    drawContent()
    val fall = light.value
    val half = Offset(fall.x * size.width, fall.y * size.height) / 2f
    val center = Offset(size.width / 2, size.height / 2)
    val outline = shape.createOutline(size, layoutDirection, this)
    drawOutline(outline, BEZEL, style = Stroke(FrostMatte.BORDER_WIDTH.dp.toPx() * 2))
    drawOutline(
        outline,
        Brush.linearGradient(
            0f to rim,
            0.45f to rim.copy(alpha = rim.alpha * 0.12f),
            1f to Color.Transparent,
            start = center - half,
            end = center + half,
        ),
        style = Stroke(FrostMatte.BORDER_WIDTH.dp.toPx() * 2),
    )
}

/**
 * Inflation: the glass bulges like a pillow. The edge facing the light glows, the far edge sinks into
 * shade and a soft specular bloom sits towards the light, all moving as the phone tilts.
 */
private fun Modifier.inflate(shape: Shape, light: State<FrostMatte.Fall>): Modifier = this
    .drawBehind {
        val fall = light.value
        drawRect(
            Brush.radialGradient(
                0f to Color.White.copy(alpha = 0.13f),
                1f to Color.Transparent,
                center = Offset(size.width * (0.5f - fall.x * 0.3f), size.height * (0.5f - fall.y * 0.45f)),
                radius = min(size.width, size.height).coerceAtLeast(1f) * 0.9f,
            ),
        )
    }
    .innerShadow(shape) {
        val fall = light.value
        color = Color.White
        alpha = 0.16f
        radius = 8.dp.toPx()
        offset = Offset(fall.x, fall.y) * 5.dp.toPx()
    }
    .innerShadow(shape) {
        val fall = light.value
        color = Color.Black
        alpha = 0.5f
        radius = 14.dp.toPx()
        offset = -Offset(fall.x, fall.y) * 7.dp.toPx()
    }

/** A glass pane: a teal glow on the floor, translucent aqua glass (or a tinted [fill]), inflation, grain, rim. */
fun Modifier.frost(
    palette: FrostMatte.Palette,
    shape: Shape,
    light: State<FrostMatte.Fall>,
    fill: Color? = null,
    height: Float = Depth.CARD,
    ring: Boolean = false,
): Modifier =
    this
        .depth(shape, height, palette.shadow.color(), light, ring)
        .clip(shape)
        // Opaque under the glass: otherwise the glow shows through, floods the pane and text loses contrast.
        .background(palette.glassFallback.color())
        .then(if (fill != null) Modifier.background(fill) else Modifier)
        .background(Brush.verticalGradient(0f to palette.glassSheen.color(), 1f to palette.glassFill.color()))
        .inflate(shape, light)
        .drawWithContent {
            drawContent()
            drawRect(grain, alpha = FrostMatte.GRAIN_ALPHA / 2)
        }
        .rim(shape, palette.glassBorder.color(), light)

/** Lets a carousel run [by] past its parent's padding to the screen edges, so glows are not cut off at the margin. */
fun Modifier.bleed(by: Dp): Modifier = layout { measurable, constraints ->
    val extra = by.roundToPx()
    val width = constraints.maxWidth + extra * 2
    val placeable = measurable.measure(constraints.copy(minWidth = width, maxWidth = width))
    layout(constraints.maxWidth, placeable.height) { placeable.place(-extra, 0) }
}

/** Fades a scrolling list out at its top and bottom instead of cutting it off against the bars. */
fun Modifier.softEdges(fade: Dp = 24.dp): Modifier = this
    .graphicsLayer { compositingStrategy = CompositingStrategy.Offscreen }
    .drawWithContent {
        drawContent()
        val share = (fade.toPx() / size.height.coerceAtLeast(1f)).coerceAtMost(0.5f)
        drawRect(
            Brush.verticalGradient(0f to Color.Transparent, share to Color.Black, 1 - share to Color.Black, 1f to Color.Transparent),
            blendMode = BlendMode.DstIn,
        )
    }

/** A neumorphic recess pressed into the glass: shaded on the lip facing the light, lit on the far one. */
fun Modifier.well(shape: Shape, light: State<FrostMatte.Fall>): Modifier = this
    .clip(shape)
    .background(Color(FrostMatte.WELL))
    .innerShadow(shape) {
        val fall = light.value
        color = Color.Black
        alpha = 0.9f
        radius = 5.dp.toPx()
        offset = Offset(fall.x, fall.y) * 3.dp.toPx()
    }
    .innerShadow(shape) {
        val fall = light.value
        color = BEZEL.copy(alpha = 1f)
        alpha = 0.2f
        radius = 3.dp.toPx()
        offset = -Offset(fall.x, fall.y) * 1.5.dp.toPx()
    }

/** A face that bulges like a balloon: a bright top edge, a shaded underside and a gloss across its upper half. */
private fun Modifier.inflated(shape: Shape, top: Color, middle: Color, bottom: Color, shine: Float = 1f): Modifier = this
    .clip(shape)
    .background(Brush.verticalGradient(0f to top, 0.45f to middle, 1f to bottom))
    .drawBehind {
        val inset = size.height * 0.05f
        val height = size.height * 0.46f
        drawRoundRect(
            Brush.verticalGradient(
                0f to Color.White.copy(alpha = 0.3f * shine),
                1f to Color.Transparent,
                startY = inset,
                endY = inset + height,
            ),
            topLeft = Offset(size.height * 0.2f, inset),
            size = Size(size.width - size.height * 0.4f, height),
            cornerRadius = CornerRadius(height / 2),
        )
    }
    .innerShadow(shape) {
        color = Color.White
        alpha = 0.55f * shine
        radius = 3.dp.toPx()
        offset = Offset(0f, 1.5.dp.toPx())
    }
    .innerShadow(shape) {
        color = Color.Black
        alpha = 0.3f
        radius = 7.dp.toPx()
        offset = Offset(0f, -3.dp.toPx())
    }

/** The raised glass of a secondary control, from its lit top to its shaded underside. */
private val GLASS_TOP = Color(0xFF2E5352)
private val GLASS_MIDDLE = Color(0xFF1A3433)
private val GLASS_BOTTOM = Color(0xFF0E2120)

/** An icon on a small inflated glass bead. Decorative: name the thing in the text beside it. */
@Composable
fun IconOrb(icon: ImageVector, modifier: Modifier = Modifier, tint: Color = FrostTheme.palette.accent.color(), size: Dp = 44.dp) {
    val glow = FrostTheme.palette.shadow.color()
    Box(
        modifier
            .size(size)
            .dropShadow(CircleShape) {
                radius = 10.dp.toPx()
                offset = Offset(0f, 3.dp.toPx())
                color = glow
                alpha = 0.5f
            }
            .inflated(CircleShape, GLASS_TOP, GLASS_MIDDLE, GLASS_BOTTOM, shine = 0.35f),
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
 * The standard card. Clickable cards are tactile: pressing sinks the pane towards the floor, its
 * shadow shortening as it goes. [fill] replaces the glass for a tinted notice; [contentPadding] 0 lets
 * a ListItem pad itself.
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
            .frost(
                FrostTheme.palette,
                shape,
                LocalLight.current,
                fill,
                height = if (pressed) Depth.CARD / 3 else Depth.CARD,
            )
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
 * Live progress as a groove pressed into the glass, filled with aqua, with an orange spark on its
 * leading edge. With no progress yet the spark waits at the top, ready to go.
 */
@Composable
fun EnergyRing(progress: Float, modifier: Modifier = Modifier, content: @Composable BoxScope.() -> Unit) {
    val palette = FrostTheme.palette
    val aqua = palette.accent.color()
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
                drawCircle(aqua.copy(alpha = 0.28f), radius + width / 2, style = Stroke(1.dp.toPx()))
                drawCircle(Color.Black, radius - width / 2, style = Stroke(1.dp.toPx()))
                if (swept > 0f) {
                    rotate(-90f) {
                        drawArc(
                            Brush.sweepGradient(0f to aqua.copy(alpha = 0.55f), swept to aqua),
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
                val burst = width * 1.9f
                val halo = Brush.radialGradient(0f to spark.copy(alpha = 0.7f), 1f to Color.Transparent, center = tip, radius = burst)
                drawCircle(halo, burst, tip)
                drawCircle(spark, width * 0.6f, tip)
                drawCircle(Color.White.copy(alpha = 0.75f), width * 0.18f, tip - Offset(width * 0.18f, width * 0.2f))
            },
        contentAlignment = Alignment.Center,
        content = content,
    )
}

class FrostBarItem(val label: String, val icon: ImageVector, val selected: Boolean, val onClick: () -> Unit)

/** How the active key travels between tabs: quick, with a little overshoot, like a sprung lever. */
private val leverSpring = spring<Float>(dampingRatio = 0.72f, stiffness = Spring.StiffnessMediumLow)

/**
 * Floating tab bar: a glass capsule hovering highest above the floor, ringed so it stays crisp over
 * any content. The current tab sits on an inflated aqua key that slides from tab to tab; the others are
 * icons only, named for screen readers.
 */
@Composable
fun FrostBar(items: List<FrostBarItem>, modifier: Modifier = Modifier) {
    val palette = FrostTheme.palette
    val key = RoundedCornerShape(FrostMatte.Radius.PILL.dp)
    // Each tab's x and width in px as laid out, so the key can travel between them.
    val slots = remember { mutableStateMapOf<Int, Pair<Float, Float>>() }
    val target = slots[items.indexOfFirst { it.selected }]
    val keyX = remember { Animatable(0f) }
    val keyWidth = remember { Animatable(0f) }
    LaunchedEffect(target) {
        if (target == null) return@LaunchedEffect
        if (keyWidth.value == 0f) {
            keyX.snapTo(target.first)
            keyWidth.snapTo(target.second)
        } else {
            launch { keyX.animateTo(target.first, leverSpring) }
            keyWidth.animateTo(target.second, leverSpring)
        }
    }
    Box(
        modifier
            .fillMaxWidth()
            .padding(horizontal = FrostMatte.Spacing.L.dp, vertical = FrostMatte.Spacing.S.dp)
            .frost(
                palette,
                RoundedCornerShape(FrostMatte.Radius.PILL.dp),
                LocalLight.current,
                height = Depth.FLOAT,
                ring = true,
            )
            .height(68.dp)
            .padding(horizontal = FrostMatte.Spacing.S.dp),
        contentAlignment = Alignment.CenterStart,
    ) {
        if (target != null) {
            // Read in the layout phase, so the slide moves the key without recomposing the bar.
            Box(
                Modifier
                    .layout { measurable, _ ->
                        val width = keyWidth.value.roundToInt()
                        val placeable = measurable.measure(Constraints.fixed(width, 48.dp.roundToPx()))
                        layout(width, placeable.height) { placeable.place(keyX.value.roundToInt(), 0) }
                    }
                    .accentKey(key),
            )
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            items.forEachIndexed { index, item ->
                val tint by animateColorAsState(
                    if (item.selected) palette.onAccent.color() else palette.textMuted.color(),
                    label = "tab tint",
                )
                Row(
                    Modifier
                        .onPlaced { slots[index] = it.positionInParent().x to it.size.width.toFloat() }
                        .clip(key)
                        .selectable(selected = item.selected, role = Role.Tab, onClick = item.onClick)
                        .height(48.dp)
                        .padding(horizontal = 14.dp)
                        .semantics(mergeDescendants = true) { contentDescription = item.label },
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Icon(item.icon, contentDescription = null, tint = tint, modifier = Modifier.size(22.dp))
                    AnimatedVisibility(item.selected, enter = fadeIn() + expandHorizontally(), exit = fadeOut() + shrinkHorizontally()) {
                        Text(
                            item.label,
                            color = tint,
                            style = MaterialTheme.typography.labelLarge,
                            modifier = Modifier.padding(start = 8.dp),
                        )
                    }
                }
            }
        }
    }
}

/** An inflated aqua face: the active tab and the player's own row. */
fun Modifier.accentKey(shape: Shape): Modifier =
    inflated(shape, Color(FrostMatte.ACCENT_TOP), Color(FrostMatte.dark.accent), Color(FrostMatte.ACCENT_BASE))

private enum class KeyTone { ENERGY, ACCENT, GLASS }

private class KeyLook(val glow: Color, val glowAlpha: Float, val ink: Color, val face: Modifier)

private fun keyLook(tone: KeyTone, palette: FrostMatte.Palette, shape: Shape) = when (tone) {
    KeyTone.ENERGY -> KeyLook(
        palette.energy.color(),
        0.6f,
        palette.onEnergy.color(),
        Modifier.inflated(shape, Color(FrostMatte.ENERGY_TOP), palette.energy.color(), Color(FrostMatte.ENERGY_BASE)),
    )
    KeyTone.ACCENT -> KeyLook(palette.accent.color(), 0.35f, palette.onAccent.color(), Modifier.accentKey(shape))
    KeyTone.GLASS -> KeyLook(
        palette.shadow.color(),
        0.35f,
        palette.textPrimary.color(),
        Modifier.inflated(shape, GLASS_TOP, GLASS_MIDDLE, GLASS_BOTTOM, shine = 0.35f),
    )
}

/**
 * A chunky inflated key that glows in its own colour. Pressing gives under the finger: it shrinks, sinks
 * and its glow pulls in, then it springs back.
 */
@Composable
private fun Key(onClick: () -> Unit, modifier: Modifier, enabled: Boolean, tone: KeyTone, content: @Composable RowScope.() -> Unit) {
    val palette = FrostTheme.palette
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val scale by pressScale(pressed && enabled, Depth.PRESS_SCALE)
    val sink by animateFloatAsState(if (pressed && enabled) 1f else 0f, spring(stiffness = Spring.StiffnessHigh), label = "sink")
    val shape = RoundedCornerShape(FrostMatte.Radius.PILL.dp)
    val look = keyLook(tone, palette, shape)
    Row(
        modifier
            .defaultMinSize(minHeight = FrostMatte.MIN_TOUCH_TARGET.dp)
            .graphicsLayer {
                scaleX = scale
                scaleY = scale
                translationY = sink * 2.dp.toPx()
                alpha = if (enabled) 1f else 0.4f
            }
            .dropShadow(shape) {
                radius = (18 - 10 * sink).dp.toPx()
                offset = Offset(0f, (6 * (1 - sink)).dp.toPx())
                color = look.glow
                alpha = look.glowAlpha
            }
            .then(look.face)
            .clickable(interactionSource = interaction, indication = null, enabled = enabled, role = Role.Button, onClick = onClick)
            .padding(horizontal = 22.dp, vertical = 4.dp),
        horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        CompositionLocalProvider(LocalContentColor provides look.ink, LocalTextStyle provides MaterialTheme.typography.labelLarge) {
            content()
        }
    }
}

/** A screen's main action, in aqua. Set [energy] on the one action that starts effort, and only that one. */
@Composable
fun KeyButton(
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    energy: Boolean = false,
    content: @Composable RowScope.() -> Unit,
) = Key(onClick, modifier, enabled, if (energy) KeyTone.ENERGY else KeyTone.ACCENT, content)

/** A secondary action, as raised glass. */
@Composable
fun RaisedButton(onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true, content: @Composable RowScope.() -> Unit) =
    Key(onClick, modifier, enabled, KeyTone.GLASS, content)

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
                .frost(palette, pill, LocalLight.current, Color(0xF2102424), Depth.FLOAT, ring = true)
                .padding(horizontal = 20.dp, vertical = 12.dp),
        )
    }
}
