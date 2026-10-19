package com.osiris.shared.data.repository

import com.osiris.shared.core.error.AppError
import com.osiris.shared.core.error.Outcome
import com.osiris.shared.core.error.outcomeOf
import com.osiris.shared.data.network.api.MeApi
import com.osiris.shared.domain.model.BlockEntry
import com.osiris.shared.domain.repository.AuthRepository
import com.osiris.shared.domain.repository.PrivacyRepository
import kotlinx.serialization.json.JsonObject

class PrivacyRepositoryImpl(
    private val me: MeApi,
    private val auth: AuthRepository,
) : PrivacyRepository {
    override suspend fun blocks(): Outcome<List<BlockEntry>> = outcomeOf { me.blocks() }

    override suspend fun unblock(blockId: Int): Outcome<Unit> = outcomeOf { me.unblock(blockId) }

    override suspend fun export(): Outcome<JsonObject> = outcomeOf { me.export() }

    override suspend fun erase(password: String): Outcome<Unit> = outcomeOf {
        if (password.isEmpty()) throw AppError.Validation("Enter your password to confirm.")
        me.erase(password)
        auth.logout()
    }

    override suspend fun rules(): Outcome<JsonObject> = outcomeOf { me.rules() }
}
