package com.osiris.player.ui.arise

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb

/** One colour per activity, shared by the map lines and the legend. */
object ActivityColors {
    val byActivity = linkedMapOf(
        "run" to Color(0xFFFF6A1A),
        "walk" to Color(0xFF29B6F6),
        "hike" to Color(0xFFFFB300),
        "trail" to Color(0xFFAB47BC),
    )
    private val other = Color.Gray
    private const val RGB = 0xFFFFFF

    fun of(activity: String): Color = byActivity[activity] ?: other

    /** Mapbox `match` expression on the `activity` property. */
    val matchExpression: String = buildString {
        append("""["match",["get","activity"]""")
        byActivity.forEach { (name, color) -> append(",\"$name\",\"${hex(color)}\"") }
        append(",\"${hex(other)}\"]")
    }

    private fun hex(c: Color) = "#%06X".format(c.toArgb() and RGB)
}
