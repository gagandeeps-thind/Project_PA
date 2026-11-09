package com.osiris.shared.presentation.social

import com.osiris.shared.domain.model.ContentReportReason
import com.osiris.shared.domain.model.ReportKind
import com.osiris.shared.domain.model.ReportTarget
import com.osiris.shared.domain.repository.SocialRepository
import com.osiris.shared.presentation.common.SharedViewModel
import com.osiris.shared.presentation.common.UiMessage
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** The question on screen: why are you reporting this, or do you want to block this player. */
sealed interface SafetyPrompt {
    data class Report(val target: ReportTarget) : SafetyPrompt
    data class Block(val userId: Int, val name: String) : SafetyPrompt
}

/** [blockedUserId] is set once a block lands, so the screen can leave or reload. */
data class ContentSafetyState(val prompt: SafetyPrompt? = null, val blockedUserId: Int? = null)

/** Report and block, from any screen that shows other players' posts, comments or messages. */
class ContentSafetyViewModel(
    private val social: SocialRepository,
    dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
) : SharedViewModel(dispatcher) {
    private val _state = MutableStateFlow(ContentSafetyState())
    val state: StateFlow<ContentSafetyState> = _state.asStateFlow()

    fun askReport(kind: ReportKind, id: Int) = _state.update { it.copy(prompt = SafetyPrompt.Report(ReportTarget(kind, id))) }

    fun askBlock(userId: Int, name: String) = _state.update { it.copy(prompt = SafetyPrompt.Block(userId, name)) }

    fun dismiss() = _state.update { it.copy(prompt = null) }

    fun report(reason: ContentReportReason) {
        val prompt = _state.value.prompt as? SafetyPrompt.Report ?: return
        dismiss()
        scope.launch { social.report(prompt.target, reason).orShow()?.let { show(it, UiMessage.Kind.SUCCESS) } }
    }

    fun confirmBlock() {
        val prompt = _state.value.prompt as? SafetyPrompt.Block ?: return
        dismiss()
        scope.launch {
            social.block(prompt.userId).orShow() ?: return@launch
            show("${prompt.name} is blocked. You can undo this in Settings.", UiMessage.Kind.SUCCESS)
            _state.update { it.copy(blockedUserId = prompt.userId) }
        }
    }

    fun blockHandled() = _state.update { it.copy(blockedUserId = null) }
}
