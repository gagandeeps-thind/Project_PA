package com.osiris.player.ui.map

import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.osiris.player.R
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.domain.model.ChallengeSummary
import com.osiris.shared.domain.model.CourseRoute
import com.osiris.shared.domain.run.LatLng
import org.osmdroid.tileprovider.tilesource.TileSourceFactory
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.CustomZoomButtonsController
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.CopyrightOverlay
import org.osmdroid.views.overlay.Marker
import org.osmdroid.views.overlay.Polygon
import org.osmdroid.views.overlay.Polyline

/**
 * OpenStreetMap view (osmdroid) with the challenge course, its start and finish zones, the live
 * trace, nearby challenge markers and the player's position. Overlays are created once and
 * updated in place, so a new GPS fix does not rebuild the map.
 */
@Composable
fun OsmMap(
    position: LatLng?,
    course: CourseRoute?,
    trace: List<LatLng>,
    nearby: List<ChallengeSummary>,
    follow: Boolean,
    onChallenge: ((Int) -> Unit)?,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val map = remember {
        MapView(context).apply {
            setTileSource(TileSourceFactory.MAPNIK)
            setMultiTouchControls(true)
            zoomController.setVisibility(CustomZoomButtonsController.Visibility.NEVER)
            controller.setZoom(16.0)
            overlays += CopyrightOverlay(context)
        }
    }
    val layers = remember { Layers(map) }

    val lifecycle = LocalLifecycleOwner.current.lifecycle
    DisposableEffect(lifecycle) {
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_RESUME -> map.onResume()
                Lifecycle.Event.ON_PAUSE -> map.onPause()
                else -> Unit
            }
        }
        lifecycle.addObserver(observer)
        onDispose {
            lifecycle.removeObserver(observer)
            map.onDetach()
        }
    }

    // MapView draws outside its bounds unless clipped, which put tiles under the top bar.
    AndroidView(factory = { map }, modifier = modifier.clipToBounds()) {
        layers.course(course)
        layers.trace(trace)
        layers.onChallenge = onChallenge
        layers.nearby(nearby)
        layers.me(position, follow)
        it.invalidate()
    }
}

private class Layers(private val map: MapView) {
    private val courseLine = Polyline(map).apply { outlinePaint.color = OsirisColors.Secondary.copy(alpha = 0.7f).toArgb(); outlinePaint.strokeWidth = 14f }
    private val startZone = zone(OsirisColors.Success)
    private val finishZone = zone(OsirisColors.Error)
    private val traceLine = Polyline(map).apply { outlinePaint.color = OsirisColors.Primary.toArgb(); outlinePaint.strokeWidth = 10f }
    private val me = Marker(map).apply {
        setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_CENTER)
        icon = ContextCompat.getDrawable(map.context, R.drawable.ic_my_location)
        setInfoWindow(null)
    }
    private val markers = mutableListOf<Marker>()
    private var nearbyIds: List<Int> = emptyList()
    private var centred = false
    private var courseShown: CourseRoute? = null
    private var traceSize = -1

    init {
        map.overlays.addAll(listOf(startZone, finishZone, courseLine, traceLine))
    }

    fun course(course: CourseRoute?) {
        if (course == courseShown) return
        courseShown = course
        val route = course?.route.orEmpty()
        val shown = route.size >= 2
        courseLine.setPoints(if (shown) route.map(::geo) else emptyList())
        startZone.setPoints(if (shown) Polygon.pointsAsCircle(geo(route.first()), course!!.startRadiusM) else emptyList())
        finishZone.setPoints(if (shown) Polygon.pointsAsCircle(geo(route.last()), course!!.startRadiusM) else emptyList())
    }

    fun trace(trace: List<LatLng>) {
        if (trace.size == traceSize) return
        // The trace only grows during a run; append instead of copying it on every fix.
        if (trace.size == traceSize + 1 && traceSize > 0) traceLine.addPoint(geo(trace.last())) else traceLine.setPoints(trace.map(::geo))
        traceSize = trace.size
    }

    /** Tapping a marker opens the challenge; [onChallenge] is null while a run records. */
    var onChallenge: ((Int) -> Unit)? = null

    fun nearby(list: List<ChallengeSummary>) {
        val ids = list.map { it.id }
        if (ids == nearbyIds) return
        nearbyIds = ids
        map.overlays.removeAll(markers)
        markers.clear()
        for (c in list) {
            markers += Marker(map).apply {
                position = geo(c.marker)
                title = c.title
                icon = ContextCompat.getDrawable(map.context, R.drawable.ic_trophy)
                setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_BOTTOM)
                setOnMarkerClickListener { _, _ ->
                    onChallenge?.invoke(c.id)
                    true
                }
            }
        }
        map.overlays.addAll(map.overlays.indexOf(traceLine) + 1, markers)
    }

    fun me(position: LatLng?, follow: Boolean) {
        if (position == null) {
            map.overlays.remove(me)
            return
        }
        me.position = geo(position)
        if (me !in map.overlays) map.overlays += me
        // Re-centre when the position leaves the view too, so a stale cached first fix is not kept.
        val offScreen = map.isLayoutOccurred && !map.boundingBox.contains(me.position)
        if (!centred || follow || offScreen) centre()
    }

    /** Before the first layout the map has no size, so centring waits for it. */
    private fun centre() {
        centred = true
        if (map.isLayoutOccurred) {
            map.controller.setCenter(me.position)
        } else {
            map.addOnFirstLayoutListener { _, _, _, _, _ -> map.controller.setCenter(me.position) }
        }
    }

    private fun zone(color: Color) = Polygon(map).apply {
        fillPaint.color = color.copy(alpha = 0.22f).toArgb()
        outlinePaint.color = color.toArgb()
        outlinePaint.strokeWidth = 4f
        setOnClickListener { _, _, _ -> false }
    }

    private fun geo(p: LatLng) = GeoPoint(p.lat, p.lng)
}

