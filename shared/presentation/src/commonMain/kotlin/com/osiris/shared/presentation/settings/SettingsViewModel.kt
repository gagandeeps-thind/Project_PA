package com.osiris.shared.presentation.settings

import com.osiris.shared.domain.model.BlockEntry
import com.osiris.shared.domain.model.Goal
import com.osiris.shared.domain.model.PlayerProfile
import com.osiris.shared.domain.model.ReferralSummary
import com.osiris.shared.domain.repository.AuthRepository
import com.osiris.shared.domain.repository.ExerciseRepository
import com.osiris.shared.domain.repository.PlayerRepository
import com.osiris.shared.domain.repository.PrivacyRepository
import com.osiris.shared.presentation.common.Loadable
import com.osiris.shared.presentation.common.ShareRequest
import com.osiris.shared.presentation.common.SharedViewModel
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonPrimitive

/** One section of the rules page. */
data class RulesSection(val title: String, val lines: List<String>)

data class SettingsState(
    val profile: Loadable<PlayerProfile> = Loadable.Loading,
    val referral: Loadable<ReferralSummary> = Loadable.Loading,
    val exerciseConsent: Boolean = false,
    val blocks: List<BlockEntry>? = null,
    val rules: List<RulesSection>? = null,
    /** Text for the platform to share or copy (invite link, data export). */
    val share: ShareRequest? = null,
    val busy: Boolean = false,
) {
    val goals: List<Goal> get() = Goal.entries

    /** "an athlete", "a runner". */
    val identityLine: String
        get() = profile.valueOrNull?.identity?.let { id ->
            val article = if (id.firstOrNull()?.lowercaseChar() in "aeiou".toSet()) "an" else "a"
            "Goal  •  you are $article $id"
        } ?: ""
}

/** Profile, privacy switches, invites, safety, data export, sign-out and account erasure. */
class SettingsViewModel(
    private val auth: AuthRepository,
    private val player: PlayerRepository,
    private val privacy: PrivacyRepository,
    private val exercises: ExerciseRepository,
    dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
) : SharedViewModel(dispatcher) {
    private val _state = MutableStateFlow(SettingsState())
    val state: StateFlow<SettingsState> = _state.asStateFlow()
    private val pretty = Json { prettyPrint = true }

    init {
        refresh()
    }

    fun refresh() {
        scope.launch { _state.update { it.copy(profile = Loadable.of(player.profile())) } }
        scope.launch { _state.update { it.copy(referral = Loadable.of(player.referrals())) } }
        scope.launch { _state.update { it.copy(exerciseConsent = exercises.consent()) } }
    }

    fun setDisplayName(name: String) = update("display_name", JsonPrimitive(name.trim()), valid = name.trim().length in 2..30)
    fun setGoal(goal: Goal) = update("goal", JsonPrimitive(goal.wire))
    fun setCity(city: String) = update("city", JsonPrimitive(city.trim()))
    fun setLocationConsent(on: Boolean) = update("location_consent", JsonPrimitive(on))
    fun setLeaderboardOptIn(on: Boolean) = update("leaderboard_opt_in", JsonPrimitive(on))
    fun setPublicProfile(on: Boolean) = update("public_profile", JsonPrimitive(on))

    /** Withdrawing with [deleteData] also erases the sets on the server and on this phone. */
    fun setExerciseConsent(granted: Boolean, deleteData: Boolean = false) {
        scope.launch {
            exercises.setConsent(granted, deleteData).orShow()?.let { now -> _state.update { it.copy(exerciseConsent = now) } }
        }
    }

    fun shareInvite() {
        val r = _state.value.referral.valueOrNull ?: return
        val text = "Join me on Osiris: daily running and walking quests. Use my code ${r.code}. ${r.url}"
        _state.update { it.copy(share = ShareRequest(text, "referral")) }
    }

    fun exportData() {
        scope.launch {
            val data = privacy.export().orShow() ?: return@launch
            val runs = (data["runs"] as? JsonArray)?.size ?: 0
            _state.update { it.copy(share = ShareRequest(pretty.encodeToString(JsonObject.serializer(), data), "export")) }
            show("Your data ($runs runs and everything else) is ready. Save it to a file to keep it.")
        }
    }

    fun shared(completed: Boolean) {
        val request = _state.value.share ?: return
        _state.update { it.copy(share = null) }
        if (completed && request.kind != "export") scope.launch { player.track("share_completed", mapOf("kind" to request.kind)) }
    }

    fun loadBlocks() {
        scope.launch { privacy.blocks().orShow()?.let { list -> _state.update { it.copy(blocks = list) } } }
    }

    fun unblock(id: Int) {
        scope.launch {
            privacy.unblock(id).orShow() ?: return@launch
            _state.update { s -> s.copy(blocks = s.blocks?.filterNot { it.id == id }) }
        }
    }

    fun loadRules() {
        scope.launch {
            val rules = privacy.rules().orShow() ?: return@launch
            _state.update { it.copy(rules = rulesSections(rules)) }
        }
    }

    fun signOutEverywhere() {
        scope.launch { auth.signOutEverywhere().orShow()?.let { show("Other devices have been signed out.") } }
    }

    fun logout() {
        scope.launch { auth.logout() }
    }

    /** On success the player is signed out and the app root shows sign-in. */
    fun erase(password: String) {
        if (_state.value.busy) return
        _state.update { it.copy(busy = true) }
        scope.launch {
            privacy.erase(password).orShow()
            _state.update { it.copy(busy = false) }
        }
    }

    private fun update(field: String, value: JsonElement, valid: Boolean = true) {
        if (!valid) return show("Names need 2 to 30 characters.")
        scope.launch {
            val updated = player.updateProfile(buildJsonObject { put(field, value) }).orShow() ?: return@launch
            _state.update { it.copy(profile = Loadable.Ready(updated)) }
        }
    }

    companion object {
        private val RULE_TITLES = listOf(
            "rewards" to "Rewards and refunds",
            "referrals" to "Inviting friends",
            "verification" to "How runs are checked",
            "leaderboards" to "Leaderboards",
            "privacy" to "Privacy",
            "safety" to "Safety",
        )

        fun rulesSections(rules: JsonObject): List<RulesSection> = RULE_TITLES.map { (key, title) ->
            RulesSection(title, (rules[key] as? JsonArray)?.mapNotNull { it.jsonPrimitive.contentOrNull }.orEmpty())
        }
    }
}
