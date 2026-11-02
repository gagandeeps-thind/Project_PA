package com.osiris.shared.domain.repository

import com.osiris.shared.core.error.Outcome
import com.osiris.shared.domain.model.AriseRoute
import com.osiris.shared.domain.run.LatLng

/** Public routes on the Arise map. */
interface AriseRepository {
    /** Public routes near [position]; the result is kept for [cached]. */
    suspend fun nearbyRoutes(position: LatLng, radiusKm: Double = 10.0): Outcome<List<AriseRoute>>

    /** Publishes an accepted run as a public route; publishing the same run again returns it. */
    suspend fun publishRoute(runId: Int, name: String, hideEnds: Boolean): Outcome<AriseRoute>

    /** A route from the last [nearbyRoutes] result, or null. */
    fun cached(id: Int): AriseRoute?
}
