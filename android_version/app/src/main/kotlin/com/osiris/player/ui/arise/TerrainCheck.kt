package com.osiris.player.ui.arise

import java.net.HttpURLConnection
import java.net.URL
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject

/** Land cover classes (Mapbox Streets v8 `landuse` / `landuse_overlay`) that make a trail run possible. */
private val NATURAL = setOf("wood", "forest", "scrub", "national_park")
private const val RADIUS_M = 300
private const val TIMEOUT_MS = 5_000

/**
 * Whether there is forest or another natural area within 300 m, from the Mapbox Tilequery API.
 * Fails open: without an answer (offline, no token) Trail stays available and the run is still
 * verified by the server.
 */
suspend fun trailAllowed(token: String, lat: Double, lng: Double): Boolean = withContext(Dispatchers.IO) {
    if (token.isBlank()) return@withContext true
    runCatching {
        val url = URL(
            "https://api.mapbox.com/v4/mapbox.mapbox-streets-v8/tilequery/$lng,$lat.json" +
                "?radius=$RADIUS_M&limit=50&layers=landuse,landuse_overlay&access_token=$token",
        )
        val connection = (url.openConnection() as HttpURLConnection).apply {
            connectTimeout = TIMEOUT_MS
            readTimeout = TIMEOUT_MS
        }
        try {
            val features = JSONObject(connection.inputStream.bufferedReader().use { it.readText() }).getJSONArray("features")
            (0 until features.length()).any { i ->
                features.getJSONObject(i).optJSONObject("properties")?.optString("class") in NATURAL
            }
        } finally {
            connection.disconnect()
        }
    }.getOrDefault(true)
}
