package com.osiris.shared.domain.repository

import com.osiris.shared.core.error.Outcome
import com.osiris.shared.domain.model.AriseAttackResult
import com.osiris.shared.domain.model.AriseDomain
import com.osiris.shared.domain.model.AriseDomains
import com.osiris.shared.domain.model.AriseRoute
import com.osiris.shared.domain.model.AriseWorkout
import com.osiris.shared.domain.model.AriseWorkoutResult
import com.osiris.shared.domain.model.HeatCell
import com.osiris.shared.domain.model.Heatmap
import com.osiris.shared.domain.run.LatLng

/** Public routes on the Arise map. */
interface AriseRepository {
    /** Public routes near [position]; the result is kept for [cached]. */
    suspend fun nearbyRoutes(position: LatLng, radiusKm: Double = 10.0): Outcome<List<AriseRoute>>

    /** Publishes an accepted run as a public route; publishing the same run again returns it. */
    suspend fun publishRoute(runId: Int, name: String, hideEnds: Boolean): Outcome<AriseRoute>

    /** A route from the last [nearbyRoutes] result, or null. */
    fun cached(id: Int): AriseRoute?

    /** Other players' domains near [position], split into suggested and hard. */
    suspend fun nearbyDomains(position: LatLng, radiusKm: Double = 10.0): Outcome<AriseDomains>

    /** Claims the area inside an accepted loop run. Fails with code NOT_A_LOOP otherwise. */
    suspend fun claimDomain(runId: Int): Outcome<AriseDomain>

    /** Exceed: a new workout for the owner's domain. */
    suspend fun exceed(domainId: Int): Outcome<AriseWorkout>

    suspend fun completeExceed(domainId: Int): Outcome<AriseWorkoutResult>

    /** Attacks [domainId] with an accepted run; the result is kept for [cachedAttack]. */
    suspend fun attack(domainId: Int, runId: Int): Outcome<AriseAttackResult>

    suspend fun completeAttack(attackId: Int): Outcome<AriseAttackResult>

    fun cachedAttack(attackId: Int): AriseAttackResult?

    /** A domain from the last [nearbyDomains] result, or null. */
    fun cachedDomain(id: Int): AriseDomain?

    /** Heatmap cells of [kind] inside the box. */
    suspend fun heatmap(kind: Heatmap, south: Double, west: Double, north: Double, east: Double): Outcome<List<HeatCell>>

    /** The owner's JPEG photo for a domain, base64-encoded. */
    suspend fun setPhoto(domainId: Int, jpegBase64: String): Outcome<AriseDomain>
}
