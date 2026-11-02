package com.osiris.shared.data.repository

import com.osiris.shared.core.error.Outcome
import com.osiris.shared.core.error.outcomeOf
import com.osiris.shared.data.network.api.AriseApi
import com.osiris.shared.domain.model.AriseAttackResult
import com.osiris.shared.domain.model.AriseDomain
import com.osiris.shared.domain.model.AriseDomains
import com.osiris.shared.domain.model.AriseRoute
import com.osiris.shared.domain.model.AriseWorkout
import com.osiris.shared.domain.model.AriseWorkoutResult
import com.osiris.shared.domain.model.HeatCell
import com.osiris.shared.domain.model.Heatmap
import com.osiris.shared.domain.repository.AriseRepository
import com.osiris.shared.domain.run.LatLng

class AriseRepositoryImpl(private val api: AriseApi) : AriseRepository {
    private var last: List<AriseRoute> = emptyList()
    private val attacks = mutableMapOf<Int, AriseAttackResult>()
    private var domains: List<AriseDomain> = emptyList()

    override suspend fun nearbyRoutes(position: LatLng, radiusKm: Double): Outcome<List<AriseRoute>> =
        outcomeOf { api.routes(position.lat, position.lng, radiusKm).also { last = it } }

    override suspend fun publishRoute(runId: Int, name: String, hideEnds: Boolean): Outcome<AriseRoute> =
        outcomeOf { api.publish(runId, name, hideEnds) }

    override fun cached(id: Int): AriseRoute? = last.firstOrNull { it.id == id }

    override suspend fun nearbyDomains(position: LatLng, radiusKm: Double): Outcome<AriseDomains> =
        outcomeOf { api.domains(position.lat, position.lng, radiusKm).also { domains = it.suggested + it.hard } }

    override suspend fun claimDomain(runId: Int): Outcome<AriseDomain> = outcomeOf { api.claim(runId) }

    override suspend fun exceed(domainId: Int): Outcome<AriseWorkout> = outcomeOf { api.exceed(domainId) }

    override suspend fun completeExceed(domainId: Int): Outcome<AriseWorkoutResult> = outcomeOf { api.completeExceed(domainId) }

    override suspend fun attack(domainId: Int, runId: Int): Outcome<AriseAttackResult> =
        outcomeOf { api.attack(domainId, runId).also { attacks[it.attackId] = it } }

    override suspend fun completeAttack(attackId: Int): Outcome<AriseAttackResult> =
        outcomeOf { api.completeAttack(attackId).also { attacks[it.attackId] = it } }

    override fun cachedAttack(attackId: Int): AriseAttackResult? = attacks[attackId]

    override fun cachedDomain(id: Int): AriseDomain? = domains.firstOrNull { it.id == id }

    override suspend fun heatmap(kind: Heatmap, south: Double, west: Double, north: Double, east: Double): Outcome<List<HeatCell>> =
        outcomeOf { api.heatmap(kind.wire, south, west, north, east) }

    override suspend fun setPhoto(domainId: Int, jpegBase64: String): Outcome<AriseDomain> =
        outcomeOf { api.photo(domainId, jpegBase64) }
}
