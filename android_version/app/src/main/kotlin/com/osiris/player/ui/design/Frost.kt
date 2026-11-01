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
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.selection.selectable
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
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageShader
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.graphics.ShaderBrush
import androidx.compose.ui.graphics.TileMode
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawOutline
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.translate
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
import kotlin.math.abs
import kotlin.math.min
import kotlin.math.roundToInt
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
 * light, a tight contact shadow at its edge and, for floating chrome, a crisp [ring] around it.
 */
fun Modifier.depth(shape: Shape, height: Float, shadow: Color, light: State<FrostMatte.Fall>, ring: Boolean = false): Modifier =
    this
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

/** The dull bronze of a bezel all the way round; the polished edge facing the light is drawn over it. */
private val BEZEL = Color(0x8C5C3A1E)

/**
 * Brass bezel: a dull bronze ring all round, polished bright on the edge facing the light and fading
 * on the far edge. Drawn inside the clip, so each stroke is twice its visible width.
 */
private fun Modifier.rim(shape: Shape, rim: Color, light: State<FrostMatte.Fall>): Modifier = drawWithContent {
    drawContent()
    val fall = light.value
    val half = Offset(fall.x * size.width, fall.y * size.height) / 2f
    val center = Offset(size.width / 2, size.height / 2)
    val outline = shape.createOutline(size, layoutDirection, this)
    drawOutline(outline, BEZEL, style = Stroke(FrostMatte.BORDER_WIDTH.dp.toPx() * 3))
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
                0f to Color.White.copy(alpha = 0.10f),
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
        alpha = 0.6f
        radius = 14.dp.toPx()
        offset = -Offset(fall.x, fall.y) * 7.dp.toPx()
    }

/** A glass pane: a navy glow on the floor, translucent navy glass (or opaque [fill]), inflation, grain, bezel. */
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
        .then(if (fill != null) Modifier.background(fill) else Modifier)
        .background(Brush.verticalGradient(0f to palette.glassSheen.color(), 1f to palette.glassFill.color()))
        .inflate(shape, light)
        .drawWithContent {
            drawContent()
            drawRect(grain, alpha = FrostMatte.GRAIN_ALPHA / 2)
        }
        .rim(shape, palette.glassBorder.color(), light)

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

class FrostBarItem(val label: String, val icon: ImageVector, val selected: Boolean, val onClick: () -> Unit)

/** How the firebox key travels between tabs: quick, with a little overshoot, like a sprung lever. */
private val leverSpring = spring<Float>(dampingRatio = 0.72f, stiffness = Spring.StiffnessMediumLow)

/**
 * Floating tab bar: a glass slab hovering highest above the floor, ringed so it stays crisp over
 * any content. The current tab sits on a firebox key that slides from tab to tab; the others are
 * icons only, named for screen readers.
 */
@Composable
fun FrostBar(items: List<FrostBarItem>, modifier: Modifier = Modifier) {
    val palette = FrostTheme.palette
    val key = RoundedCornerShape(18.dp)
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
                RoundedCornerShape(FrostMatte.Radius.LARGE.dp),
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

/** A deep-orange face standing on its red-hot base, like a key: the active tab and the player's own row. */
fun Modifier.accentKey(shape: Shape): Modifier = this
    .drawBehind {
        val outline = shape.createOutline(size, layoutDirection, this)
        translate(0f, Depth.KEY.dp.toPx() * 0.75f) { drawOutline(outline, Color(FrostMatte.ACCENT_BASE)) }
    }
    .clip(shape)
    .background(Brush.verticalGradient(0f to Color(FrostMatte.ACCENT_TOP), 1f to Color(FrostMatte.dark.accent)))

/**
 * A chunky physical key. The face is lit from the top and stands [Depth.KEY] on its base; pressing
 * shrinks it and sinks it onto the base. [primary] keys are deep orange, the rest raised navy.
 */
@Composable
private fun Key(
    onClick: () -> Unit,
    modifier: Modifier,
    enabled: Boolean,
    primary: Boolean,
    content: @Composable RowScope.() -> Unit,
) {
    val palette = FrostTheme.palette
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val scale by pressScale(pressed && enabled, Depth.PRESS_SCALE)
    val sink by animateFloatAsState(if (pressed && enabled) 1f else 0f, spring(stiffness = Spring.StiffnessHigh), label = "sink")
    val light = LocalLight.current
    val shape = RoundedCornerShape(FrostMatte.Radius.SMALL.dp + 4.dp)
    val face = if (primary) {
        Brush.verticalGradient(0f to Color(FrostMatte.ACCENT_TOP), 1f to palette.accent.color())
    } else {
        Brush.verticalGradient(0f to Color(0xFF2A4384), 1f to Color(0xFF172757))
    }
    val base = if (primary) Color(FrostMatte.ACCENT_BASE) else Color(0xFF0A1330)
    val ink = if (primary) palette.onAccent.color() else palette.textPrimary.color()
    Row(
        modifier
            .defaultMinSize(minHeight = FrostMatte.MIN_TOUCH_TARGET.dp)
            .graphicsLayer {
                scaleX = scale
                scaleY = scale
                translationY = sink * Depth.KEY.dp.toPx()
                alpha = if (enabled) 1f else 0.4f
            }
            .depth(shape, Depth.KEY * 2 * (1 - sink), palette.shadow.color(), light)
            .drawBehind {
                // The base stays put while the face travels down onto it.
                translate(0f, (1 - sink) * Depth.KEY.dp.toPx()) { drawOutline(shape.createOutline(size, layoutDirection, this), base) }
            }
            .clip(shape)
            .background(face)
            .innerShadow(shape) {
                color = Color.White
                alpha = if (primary) 0.35f else 0.12f
                radius = 2.dp.toPx()
                offset = Offset(0f, 1.5.dp.toPx())
            }
            .clickable(interactionSource = interaction, indication = null, enabled = enabled, role = Role.Button, onClick = onClick)
            .padding(horizontal = 22.dp, vertical = 12.dp),
        horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        CompositionLocalProvider(LocalContentColor provides ink, LocalTextStyle provides MaterialTheme.typography.labelLarge) {
            content()
        }
    }
}

/** The screen's main action, as a firebox key. */
@Composable
fun KeyButton(onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true, content: @Composable RowScope.() -> Unit) =
    Key(onClick, modifier, enabled, primary = true, content)

/** A secondary action, as a raised navy key. */
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
                .frost(palette, pill, LocalLight.current, Color(0xF2142347), Depth.FLOAT, ring = true)
                .padding(horizontal = 20.dp, vertical = 12.dp),
        )
    }
}
