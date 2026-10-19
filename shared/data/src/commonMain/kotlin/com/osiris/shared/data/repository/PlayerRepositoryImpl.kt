package com.osiris.shared.data.repository

import com.osiris.shared.core.error.Outcome
import com.osiris.shared.core.error.outcomeOf
import com.osiris.shared.core.logging.Logger
import com.osiris.shared.data.network.api.MeApi
import com.osiris.shared.domain.model.PlayerProfile
import com.osiris.shared.domain.model.Progression
import com.osiris.shared.domain.model.ReferralSummary
import com.osiris.shared.domain.model.ShareCard
import com.osiris.shared.domain.model.TodayData
import com.osiris.shared.domain.repository.PlayerRepository
import com.osiris.shared.domain.run.LatLng
import kotlin.coroutines.cancellation.CancellationException
import kotlin.time.Clock
import kotlinx.serialization.json.JsonObject

class PlayerRepositoryImpl(
    private val me: MeApi,
    private val installId: InstallId,
    private val logger: Logger,
    private val clock: Clock = Clock.System,
) : PlayerRepository {
    override suspend fun today(position: LatLng?): Outcome<TodayData> = outcomeOf {
        me.today(position?.lat, position?.lng, utcOffsetMinutes(clock.now()))
    }

    override suspend fun profile(): Outcome<PlayerProfile> = outcomeOf { me.profile() }

    override suspend fun updateProfile(changes: JsonObject): Outcome<PlayerProfile> = outcomeOf { me.updateProfile(changes) }

    override suspend fun progression(): Outcome<Progression> = outcomeOf { me.progression() }

    override suspend fun referrals(): Outcome<ReferralSummary> = outcomeOf { me.referrals() }

    override suspend fun shareAchievement(kind: String, entityId: Int): Outcome<ShareCard> = outcomeOf {
        val card = me.share(kind, entityId)
        track("share_completed", mapOf("kind" to kind))
        card
    }

    override suspend fun track(event: String, properties: Map<String, String>) {
        try {
            me.track(event, installId.get(), properties)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Throwable) {
            logger.debug(TAG, "Event $event not sent: ${e.message}")
        }
    }

    private companion object {
        const val TAG = "OsirisPlayer"
    }
}
