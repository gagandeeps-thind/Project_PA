package com.osiris.shared.presentation

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

/** Handle Swift keeps to stop watching a flow (in `deinit` or `onDisappear`). */
class Watch internal constructor(private val scope: CoroutineScope) {
    fun cancel() = scope.cancel()
}

/**
 * Lets SwiftUI observe a view model's state: `vm.state.watch { state in self.state = state }`.
 * Values arrive on the main thread; the current value is delivered at once.
 */
fun <T : Any> StateFlow<T>.watch(onEach: (T) -> Unit): Watch {
    val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    scope.launch { collect { onEach(it) } }
    return Watch(scope)
}

/** Same as [watch], for flows whose value may be null (messages, dialogs). */
fun <T> StateFlow<T?>.watchOptional(onEach: (T?) -> Unit): Watch {
    val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    scope.launch { collect { onEach(it) } }
    return Watch(scope)
}
