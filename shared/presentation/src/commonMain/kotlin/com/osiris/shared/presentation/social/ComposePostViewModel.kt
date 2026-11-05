package com.osiris.shared.presentation.social

import com.osiris.shared.domain.model.FeedPost
import com.osiris.shared.domain.model.SocialPostDraft
import com.osiris.shared.domain.model.TrainingActivity
import com.osiris.shared.domain.model.TrainingSession
import com.osiris.shared.domain.repository.SocialRepository
import com.osiris.shared.domain.repository.TrainingRepository
import com.osiris.shared.presentation.common.Loadable
import com.osiris.shared.presentation.common.SharedViewModel
import com.osiris.shared.presentation.common.UiMessage
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class ComposeState(
    val sessions: Loadable<List<TrainingSession>> = Loadable.Loading,
    val activities: Map<String, TrainingActivity> = emptyMap(),
    val selected: List<Int> = emptyList(),
    val withChart: Boolean = false,
    val caption: String = "",
    /** The picked photo as a base64 JPEG (the platform shrinks it to fit 300 KB). */
    val photo: String? = null,
    val followersOnly: Boolean = false,
    val posting: Boolean = false,
    /** Set once the post is made; the screen then closes. */
    val posted: FeedPost? = null,
) {
    val draft: SocialPostDraft
        get() = SocialPostDraft(
            caption = caption,
            photoJpegBase64 = photo,
            trainingSessionIds = selected,
            chart = if (withChart) SocialPostDraft.CHART_WEEKLY else SocialPostDraft.CHART_NONE,
            visibility = if (followersOnly) "followers" else "public",
        )

    val canPost: Boolean get() = !posting && !draft.isEmpty
    val canSelectMore: Boolean get() = selected.size < SocialPostDraft.MAX_WORKOUTS

    fun activityName(key: String): String = activities[key]?.name ?: key.replaceFirstChar { it.uppercase() }

    companion object {
        const val MAX_CAPTION = 600
    }
}

/** The + composer: a photo, one or more past workouts, a progress chart, or all together. */
class ComposePostViewModel(
    private val social: SocialRepository,
    private val training: TrainingRepository,
    preselectedSessionId: Int? = null,
    dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
) : SharedViewModel(dispatcher) {
    private val _state = MutableStateFlow(ComposeState(selected = listOfNotNull(preselectedSessionId)))
    val state: StateFlow<ComposeState> = _state.asStateFlow()

    init {
        scope.launch {
            val activities = async { training.activities() }
            val sessions = training.sessions()
            val names = activities.await().orShow().orEmpty().associateBy { it.key }
            _state.update { it.copy(sessions = Loadable.of(sessions), activities = names) }
        }
    }

    fun toggleSession(id: Int) = _state.update { s ->
        when {
            id in s.selected -> s.copy(selected = s.selected - id)
            s.canSelectMore -> s.copy(selected = s.selected + id)
            else -> {
                show("Attach up to ${SocialPostDraft.MAX_WORKOUTS} workouts")
                s
            }
        }
    }

    fun toggleChart() = _state.update { it.copy(withChart = !it.withChart) }
    fun caption(text: String) = _state.update { it.copy(caption = text.take(ComposeState.MAX_CAPTION)) }
    fun photo(base64Jpeg: String?) = _state.update { it.copy(photo = base64Jpeg) }
    fun followersOnly(on: Boolean) = _state.update { it.copy(followersOnly = on) }

    fun post() {
        val s = _state.value
        if (!s.canPost) return
        _state.update { it.copy(posting = true) }
        scope.launch {
            val created = social.createPost(s.draft).orShow()
            _state.update { it.copy(posting = false, posted = created) }
            if (created != null) show("Posted", UiMessage.Kind.SUCCESS)
        }
    }
}
