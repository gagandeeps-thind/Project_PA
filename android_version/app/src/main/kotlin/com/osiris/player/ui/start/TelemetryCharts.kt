package com.osiris.player.ui.start

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.PagerState
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.TransformOrigin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.osiris.player.ui.design.FrostCard
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.domain.common.Format
import com.osiris.shared.domain.model.TrainingSession
import com.osiris.shared.domain.training.Channel
import kotlin.math.abs

private const val CUBE_DEGREES = 90f
private const val MPS_TO_KMH = 3.6
private const val AVG_DASH = 10f
private const val FADE = 0.5f
private const val HALF = 0.5f

/** One chart's numbers: points already in display units, and the summary labels. */
private class ChartData(val channel: Channel, val points: List<List<Double>>, val avg: Double?, val min: Double?, val max: Double?)

private val HrRed = Color(0xFFEF5350)
private val PowerGold = Color(0xFFFFC107)
private val SpeedBlue = Color(0xFF29B6F6)
private val ClimbGreen = Color(0xFF66BB6A)
private const val CUBE_CAMERA = 16f

private fun Channel.color(): Color = when (this) {
    Channel.HR -> HrRed
    Channel.POWER -> PowerGold
    Channel.SPEED -> SpeedBlue
    Channel.ELEVATION -> ClimbGreen
}

private fun Channel.empty(): String = when (this) {
    Channel.HR -> "Connect a heart-rate strap or watch to see this."
    Channel.POWER -> "Connect a power meter to see this."
    Channel.SPEED -> "Use GPS outdoors or a speed sensor to see this."
    Channel.ELEVATION -> "Record outdoors with GPS to see this."
}

private fun chartsOf(s: TrainingSession): List<ChartData> {
    val series = s.series
    fun avgOf(p: List<List<Double>>) = p.takeIf { it.isNotEmpty() }?.let { pts -> pts.sumOf { it[1] } / pts.size }
    val speed = series?.speed.orEmpty().map { listOf(it[0], it[1] * MPS_TO_KMH) }
    val elevation = series?.elevation.orEmpty()
    return listOf(
        ChartData(Channel.HR, series?.hr.orEmpty(), s.hrAvg, s.hrMin, s.hrMax),
        ChartData(Channel.POWER, series?.power.orEmpty(), s.powerAvg, s.powerMin, s.powerMax),
        ChartData(Channel.SPEED, speed, s.speedAvg?.times(MPS_TO_KMH), speed.minOfOrNull { it[1] }, s.speedMax?.times(MPS_TO_KMH)),
        ChartData(Channel.ELEVATION, elevation, avgOf(elevation), s.elevMin, s.elevMax),
    )
}

/**
 * Heart rate, power, speed and elevation of [session], one chart per face of a turning cube:
 * swiping rotates the next face in about the shared edge.
 */
@Composable
fun TelemetryCharts(session: TrainingSession?, modifier: Modifier = Modifier) {
    if (session == null) {
        FrostCard(modifier.fillMaxWidth()) {
            Text("No sessions yet", style = MaterialTheme.typography.titleMedium)
            Text("Finish a session to see your heart rate, power, speed and elevation here.", color = OsirisColors.Muted)
        }
        return
    }
    val charts = chartsOf(session)
    val pager = rememberPagerState { charts.size }
    Column(modifier) {
        HorizontalPager(pager, contentPadding = PaddingValues(horizontal = 4.dp)) { page ->
            ChartCard(charts[page], session.durationS, Modifier.cube(pager, page))
        }
        Row(Modifier.fillMaxWidth().padding(top = 8.dp), horizontalArrangement = Arrangement.Center) {
            charts.forEachIndexed { i, c ->
                Text(
                    c.channel.label,
                    style = MaterialTheme.typography.labelSmall,
                    color = if (i == pager.currentPage) c.channel.color() else OsirisColors.Faint,
                    modifier = Modifier.padding(horizontal = 6.dp),
                )
            }
        }
    }
}

/** The outgoing face turns away about its trailing edge as the incoming one turns in about its leading edge. */
private fun Modifier.cube(pager: PagerState, page: Int): Modifier = graphicsLayer {
    val offset = (pager.currentPage - page) + pager.currentPageOffsetFraction
    transformOrigin = TransformOrigin(if (offset < 0) 0f else 1f, HALF)
    rotationY = -offset * CUBE_DEGREES
    alpha = 1f - FADE * abs(offset).coerceAtMost(1f)
    cameraDistance = CUBE_CAMERA * density
}

@Composable
private fun ChartCard(c: ChartData, durationS: Double, modifier: Modifier) {
    val unit = c.channel.unit
    fun fmt(v: Double?) = v?.let { Format.fixed(it, if (c.channel == Channel.SPEED) 1 else 0) } ?: "—"
    FrostCard(modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.Bottom) {
            Text(c.channel.label, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
            Text(unit, color = OsirisColors.Faint)
        }
        Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), horizontalArrangement = Arrangement.SpaceBetween) {
            Stat("Avg", fmt(c.avg), c.channel.color())
            Stat("Min", fmt(c.min), null)
            Stat("Max", fmt(c.max), null)
        }
        if (c.points.size < 2) {
            Box(Modifier.fillMaxWidth().height(120.dp), contentAlignment = Alignment.Center) {
                Text(c.channel.empty(), color = OsirisColors.Muted)
            }
        } else {
            LineChart(c.points, c.avg, c.channel.color(), "${c.channel.label} over time, average ${fmt(c.avg)} $unit")
            Row(Modifier.fillMaxWidth()) {
                Text("0:00", style = MaterialTheme.typography.labelSmall, color = OsirisColors.Faint, modifier = Modifier.weight(1f))
                Text(Format.duration(durationS), style = MaterialTheme.typography.labelSmall, color = OsirisColors.Faint)
            }
        }
    }
}

@Composable
private fun Stat(label: String, value: String, color: Color?) {
    Column {
        Text(label, style = MaterialTheme.typography.labelSmall, color = OsirisColors.Muted)
        Text(value, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, color = color ?: Color.Unspecified)
    }
}

/** A line over time, scaled to the series' own range, with the average dashed across. */
@Composable
fun LineChart(points: List<List<Double>>, avg: Double?, color: Color, description: String, modifier: Modifier = Modifier) {
    Canvas(modifier.fillMaxWidth().height(120.dp).semantics { contentDescription = description }) {
        val t0 = points.first()[0]
        val t1 = points.last()[0].coerceAtLeast(t0 + 1)
        val lo = points.minOf { it[1] }
        val hi = points.maxOf { it[1] }.coerceAtLeast(lo + 1)
        fun x(t: Double) = ((t - t0) / (t1 - t0) * size.width).toFloat()
        fun y(v: Double) = (size.height - (v - lo) / (hi - lo) * size.height).toFloat()
        val path = Path().apply {
            moveTo(x(points[0][0]), y(points[0][1]))
            for (p in points.drop(1)) lineTo(x(p[0]), y(p[1]))
        }
        drawPath(path, color, style = Stroke(width = 2.dp.toPx(), cap = StrokeCap.Round))
        avg?.let {
            drawLine(
                color.copy(alpha = FADE), Offset(0f, y(it)), Offset(size.width, y(it)), strokeWidth = 1.dp.toPx(),
                pathEffect = PathEffect.dashPathEffect(floatArrayOf(AVG_DASH, AVG_DASH)),
            )
        }
    }
}
