package com.osiris.player.ui.map

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.domain.run.LatLng
import org.osmdroid.tileprovider.tilesource.TileSourceFactory
import org.osmdroid.util.BoundingBox
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.CustomZoomButtonsController
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.CopyrightOverlay
import org.osmdroid.views.overlay.Polygon
import org.osmdroid.views.overlay.Polyline

/** A fixed, non-interactive map of a course route with green start and red finish dots. */
@Composable
fun CoursePreview(route: List<LatLng>, modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val points = remember(route) { route.map { GeoPoint(it.lat, it.lng) } }
    val map = remember {
        MapView(context).apply {
            setTileSource(TileSourceFactory.MAPNIK)
            setMultiTouchControls(false)
            zoomController.setVisibility(CustomZoomButtonsController.Visibility.NEVER)
            setOnTouchListener { _, _ -> true }
            overlays += CopyrightOverlay(context)
        }
    }
    DisposableEffect(map) { onDispose { map.onDetach() } }
    AndroidView(
        factory = { map },
        modifier = modifier.fillMaxWidth().height(200.dp).clip(RoundedCornerShape(12.dp)),
    ) { view ->
        view.overlays.removeAll { it is Polyline || it is Polygon }
        view.overlays += Polyline(view).apply {
            setPoints(points)
            outlinePaint.color = OsirisColors.Secondary.toArgb()
            outlinePaint.strokeWidth = 12f
        }
        for ((point, color) in listOf(points.first() to OsirisColors.Success, points.last() to OsirisColors.Error)) {
            view.overlays += Polygon(view).apply {
                setPoints(Polygon.pointsAsCircle(point, 12.0))
                fillPaint.color = color.toArgb()
                outlinePaint.color = color.toArgb()
            }
        }
        // Fit once the view has a size; before layout the box would zoom to the whole world.
        val fit = { view.zoomToBoundingBox(BoundingBox.fromGeoPointsSafe(points).increaseByScale(1.3f), false) }
        if (view.isLayoutOccurred) fit() else view.addOnFirstLayoutListener { _, _, _, _, _ -> fit() }
        view.invalidate()
    }
}
