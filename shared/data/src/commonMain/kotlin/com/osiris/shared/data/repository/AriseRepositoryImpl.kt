package com.osiris.shared.data.repository

import com.osiris.shared.core.error.Outcome
import com.osiris.shared.core.error.outcomeOf
import com.osiris.shared.data.network.api.AriseApi
import com.osiris.shared.domain.model.AriseRoute
import com.osiris.shared.domain.repository.AriseRepository
import com.osiris.shared.domain.run.LatLng

class AriseRepositoryImpl(private val api: AriseApi) : AriseRepository {
    private var last: List<AriseRoute> = emptyList()

    override suspend fun nearbyRoutes(position: LatLng, radiusKm: Double): Outcome<List<AriseRoute>> =
        outcomeOf { api.routes(position.lat, position.lng, radiusKm).also { last = it } }

    override suspend fun publishRoute(runId: Int, name: String, hideEnds: Boolean): Outcome<AriseRoute> =
        outcomeOf { api.publish(runId, name, hideEnds) }

    override fun cached(id: Int): AriseRoute? = last.firstOrNull { it.id == id }
}
